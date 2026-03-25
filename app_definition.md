# Universal Chatbot Framework
## Architecture Proposal v1.0

**Stack:** LangGraph · FastAPI · LiteLLM · LlamaIndex  
**Persistence:** PostgreSQL — LangGraph checkpointer + pgvector store  
**Transport:** SSE · WebSocket · REST

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Three-Layer Graph Architecture](#3-three-layer-graph-architecture)
4. [State Schema](#4-state-schema)
5. [Persistence — PostgreSQL Checkpointer & pgvector](#5-persistence--postgresql-checkpointer--pgvector)
6. [Interrupt / Resume Lifecycle](#6-interrupt--resume-lifecycle)
7. [SSE Event Protocol](#7-sse-event-protocol)
8. [LLM Gateway — LiteLLM](#8-llm-gateway--litellm)
9. [RAG Tool — LlamaIndex Integration](#9-rag-tool--llamaindex-integration)
10. [Project Structure](#10-project-structure)
11. [Docker Compose](#11-docker-compose)
12. [Application Startup & Registration](#12-application-startup--registration)
13. [Frontend — UI State Machine](#13-frontend--ui-state-machine)
14. [Extending the Framework](#14-extending-the-framework)
15. [Decision Log](#15-decision-log)
16. [Production Upgrade Path](#16-production-upgrade-path)

---

## 1. Executive Summary

This document specifies the architecture for a universal chatbot backend framework. The goal is a single, well-defined codebase that can be deployed as-is for simple conversational AI use cases, and extended — without modification to its core — for arbitrarily complex ones: multi-step data collection flows, retrieval-augmented generation, scoring pipelines, or any combination thereof.

The design is built around three principles:

- **Layered extensibility.** Core execution logic is fixed. Application-specific behaviour lives in swappable subgraphs. Reusable interaction patterns live in self-contained tool graphs. No layer needs to know the internal structure of the layers below it.

- **Typed communication.** Every event crossing the backend-to-frontend boundary carries a typed envelope. The frontend can always know what mode the conversation is in, what tool is running, and what kind of input is expected next.

- **Single database for everything.** Both conversation state and vector embeddings live in PostgreSQL. LangGraph's `AsyncPostgresSaver` handles checkpointing, and LlamaIndex's `PGVectorStore` handles retrieval — the same Postgres instance, the same connection string, no additional infrastructure.

---

## 2. System Overview

### 2.1 Container layout

The system is composed of three Docker containers and two data stores, all defined in a single compose file:

| Container / Service | Technology | Responsibility |
|---|---|---|
| `frontend` | React or Vue + Vite | Chat UI, SSE event consumption, UI state machine |
| `api` | FastAPI + Uvicorn | HTTP gateway, auth middleware, graph invoker, SSE streaming |
| `engine` | LangGraph + LiteLLM + LlamaIndex | All graph execution — core, subgraphs, and tool graphs |
| `postgres` | PostgreSQL 16 + pgvector extension | LangGraph checkpoint store AND vector embeddings — single database |

The frontend never communicates with the engine directly. All traffic goes through the FastAPI container. The engine container has no public ports; it is only reachable from the API container on the internal Docker network.

> **Why a single PostgreSQL instance for both checkpoints and vectors?**
> LangGraph's `AsyncPostgresSaver` (from `langgraph-checkpoint-postgres`) and LlamaIndex's `PGVectorStore` both speak to Postgres via standard connection strings. Running them in the same instance means one container, one volume, one backup strategy, and one set of credentials. The `pgvector` extension (installed via `CREATE EXTENSION vector`) is the only requirement beyond a standard Postgres 16 image.

### 2.2 Request path overview

A user message travels the following path from browser to response and back:

1. The frontend sends `POST /api/chat` with the message text and the session ID in the request body.
2. FastAPI's auth middleware validates the request, then calls the graph invoker.
3. The graph invoker loads the conversation checkpoint from PostgreSQL using the session ID as the thread key, appends the new human message, and calls `graph.astream_events(...)`. The graph may already be in a suspended (interrupted) state from a previous turn.
4. LangGraph resumes or starts the graph. The core layer classifies intent and dispatches to the appropriate subgraph, or falls back to plain LLM chat.
5. As the graph runs, nodes emit typed SSE events. FastAPI streams these to the frontend as `text/event-stream` responses.
6. If a tool graph reaches an `interrupt()` call, the graph suspends, the full state is checkpointed to PostgreSQL, and a `tool_question` event is streamed to the frontend. The HTTP response ends.
7. The user types their answer. The next `POST /api/chat` detects the suspended checkpoint and uses `Command(resume=...)` to continue from exactly where the graph paused.

---

## 3. Three-Layer Graph Architecture

The LangGraph execution engine is organised as a strict hierarchy of three layers. Each layer is a compiled LangGraph subgraph. Layers communicate only through shared state fields that are owned by each layer's TypedDict definition. No layer can write to fields owned by a layer above it.

### 3.1 Layer 1 — Core graph

> **Ownership & modification policy:** This layer is platform-owned. Application developers must not modify it. Adding a new use case means registering a new subgraph, never editing core nodes.

The core graph contains four fixed nodes arranged in a linear pipeline with one conditional branch:

| Node | What it does |
|---|---|
| `session_manager` | Trims the message history to fit the context window. Injects system prompt. Sets session-level metadata (user ID, locale, active tool). |
| `intent_router` | Calls LiteLLM with a classification prompt built from the registered subgraph descriptions. Returns the name of the subgraph to dispatch, or `"fallback"` if nothing matches. |
| `fallback_llm` | Plain conversational LLM call via LiteLLM. Used when no subgraph matches the intent, or when a tool error ejects to the core. |
| `output_formatter` | Normalises the output from either the subgraph or the fallback LLM into a final message. Emits the `tool_complete` or `text_done` SSE event. |

The intent router is the only decision node. Its routing table is built dynamically from the registered subgraphs' `describe()` strings at application startup. This means adding a new subgraph automatically makes the router aware of it without any manual configuration.

```python
# core/graph.py

def build_core_graph(registry: SubgraphRegistry) -> CompiledGraph:
    g = StateGraph(CoreState)
    g.add_node("session_manager",  session_manager_node)
    g.add_node("intent_router",    intent_router_node(registry))
    g.add_node("fallback_llm",     fallback_llm_node)
    g.add_node("output_formatter", output_formatter_node)

    # register each subgraph as a node by name
    for name, sg in registry.items():
        g.add_node(name, sg)
        g.add_edge(name, "output_formatter")

    g.add_edge(START, "session_manager")
    g.add_edge("session_manager", "intent_router")
    g.add_conditional_edges("intent_router", route_to_subgraph_or_fallback)
    g.add_edge("fallback_llm", "output_formatter")
    g.add_edge("output_formatter", END)
    return g.compile(checkpointer=get_checkpointer())
```

### 3.2 Layer 2 — Use-case subgraphs

> **Ownership & modification policy:** Application-owned. One subgraph per use case. A subgraph defines the orchestration logic for its use case: which tools run, in what order, and under what conditions. It does not implement tool logic itself.

A subgraph is any object that implements the following protocol:

```python
# core/protocols.py

class SubgraphProtocol(Protocol):
    name: str

    def describe(self) -> str:
        """One or two sentences the intent router uses to decide
        whether to dispatch to this subgraph. Be specific."""
        ...

    def build(self) -> CompiledGraph:
        """Return a compiled LangGraph subgraph.
        Called once at application startup."""
        ...
```

Subgraphs receive and return `SubgraphState`, which extends `CoreState` with tool-orchestration fields. The subgraph may only write to its own fields.

```python
# Example: assessment subgraph (apps/assessment/subgraph.py)

class AssessmentSubgraph:
    name = "assessment"

    def __init__(self, collector: ToolGraph, analyzer: ToolGraph,
                 presenter: ToolGraph):
        self._collector  = collector
        self._analyzer   = analyzer
        self._presenter  = presenter

    def describe(self) -> str:
        return (
            "Run a structured multi-question assessment on the user, "
            "score their answers, and present the result."
        )

    def build(self) -> CompiledGraph:
        g = StateGraph(SubgraphState)
        g.add_node("collector",  self._collector.build())
        g.add_node("analyzer",   self._analyzer.build())
        g.add_node("presenter",  self._presenter.build())

        g.add_edge(START, "collector")
        g.add_conditional_edges("collector", self._after_collector)
        g.add_edge("analyzer", "presenter")
        g.add_edge("presenter", END)
        return g.compile()

    @staticmethod
    def _after_collector(state: SubgraphState) -> str:
        if state["tool_status"] == "error": return END
        return "analyzer"
```

### 3.3 Layer 3 — Tool graphs

> **Ownership & modification policy:** Tool-owned. Each tool is a self-contained compiled subgraph that implements a single reusable interaction pattern. Tools are injected into subgraphs at build time. The same tool instance can be used in multiple subgraphs.

Tools implement the same protocol as subgraphs but operate on `ToolState`, which extends `SubgraphState` with step-level fields:

```python
class ToolState(SubgraphState):
    step:        int
    step_data:   dict        # accumulated data across steps
    is_complete: bool
    error:       str | None
    # tool-specific fields added via TypedDict inheritance
```

Tools use `interrupt()` when they need user input. The return value of `interrupt()` is the user's reply on the next turn. This keeps multi-step interaction logic in a single node function rather than split across edges.

```python
# tools/data_collector/tool.py

class DataCollectorState(ToolState):
    questions:       list[str]
    questions_total: int

class DataCollectorTool:
    name = "data_collector"

    def __init__(self, questions: list[str]):
        self._questions = questions

    def describe(self) -> str:
        return "Collects structured answers to a fixed question list."

    def build(self) -> CompiledGraph:
        async def collect(state: DataCollectorState):
            await adispatch_custom_event("tool_start", {
                "tool_name":   self.name,
                "total_steps": len(self._questions),
            })
            data = {}
            for i, question in enumerate(self._questions):
                await adispatch_custom_event("tool_question", {
                    "text":       question,
                    "step":       i + 1,
                    "input_type": "free_text",
                })
                answer = interrupt(question)   # suspends; resumes with user reply
                data[f"q{i}"] = answer
                await adispatch_custom_event("tool_progress", {
                    "step": i + 1, "total": len(self._questions)
                })
            return {**state, "step_data": data, "is_complete": True}

        g = StateGraph(DataCollectorState)
        g.add_node("collect", collect)
        g.add_edge(START, "collect")
        g.add_edge("collect", END)
        return g.compile()
```

---

## 4. State Schema

The shared state is defined as a TypedDict hierarchy. Each layer extends the one above it. Fields are grouped by which layer owns them.

### 4.1 CoreState — owned by Layer 1

```python
class CoreState(TypedDict):
    # Communication
    messages:        Annotated[list[BaseMessage], add_messages]
    session_id:      str
    output:          str | None

    # Routing
    intent:          str | None       # set by intent_router
    active_subgraph: str | None       # name of currently running subgraph
    subgraph_status: Literal["idle", "running", "done", "error"]

    # Passthrough
    metadata:        dict             # session-level context (user_id, locale…)
```

### 4.2 SubgraphState — owned by Layer 2

```python
class SubgraphState(CoreState):
    active_tool:  str | None
    tool_status:  Literal["idle", "running", "done", "error"]
    tool_input:   dict      # data passed INTO the tool
    tool_output:  dict      # data returned FROM the tool
```

### 4.3 ToolState — owned by Layer 3

```python
class ToolState(SubgraphState):
    step:        int
    step_data:   dict
    is_complete: bool
    error:       str | None
    # Each concrete tool adds its own fields via TypedDict inheritance
```

### Write boundary rule

| Layer | May write to |
|---|---|
| Layer 1 — core | `messages`, `output`, `intent`, `active_subgraph`, `subgraph_status`, `metadata` |
| Layer 2 — subgraph | `active_tool`, `tool_status`, `tool_input`, `tool_output` |
| Layer 3 — tool | `step`, `step_data`, `is_complete`, `error`, and any tool-specific fields |

---

## 5. Persistence — PostgreSQL Checkpointer & pgvector

PostgreSQL serves as the single persistence layer for the entire framework. It handles two distinct concerns via two separate mechanisms, both pointing at the same database instance:

- **LangGraph checkpointer** (`langgraph-checkpoint-postgres`) — stores full conversation state, including the suspended graph execution frame, per `thread_id`.
- **LlamaIndex PGVectorStore** — stores document embeddings for RAG tool graphs, queried via pgvector's `<->` operator.

```python
# backend/engine/checkpointer.py

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import os

async def get_checkpointer() -> AsyncPostgresSaver:
    conn_string = os.environ["DATABASE_URL"]
    # DATABASE_URL = postgresql+asyncpg://user:password@postgres:5432/chatbot
    checkpointer = AsyncPostgresSaver.from_conn_string(conn_string)
    await checkpointer.setup()   # creates the checkpoint tables if they don't exist
    return checkpointer
```

```python
# backend/engine/vector_store.py

from llama_index.vector_stores.postgres import PGVectorStore
import os

def get_vector_store(table_name: str = "embeddings") -> PGVectorStore:
    return PGVectorStore.from_params(
        host     = os.environ["POSTGRES_HOST"],
        port     = int(os.environ.get("POSTGRES_PORT", 5432)),
        database = os.environ["POSTGRES_DB"],
        user     = os.environ["POSTGRES_USER"],
        password = os.environ["POSTGRES_PASSWORD"],
        table_name       = table_name,
        embed_dim        = 1536,   # match your embedding model's output dimension
        hybrid_search    = True,   # enables BM25 + vector hybrid via pgvector
    )
```

The checkpointer is passed to the top-level graph compile call only. Subgraphs and tool graphs inherit it automatically.

```python
graph = build_core_graph(registry).compile(checkpointer=await get_checkpointer())
```

The vector store is instantiated once at startup and injected into any `RAGTool` that needs it. Multiple RAG tools can target different tables in the same database — useful when different subgraphs need to search different document sets.

> **pgvector setup:** The `postgres` service uses the `pgvector/pgvector:pg16` Docker image, which ships with the extension pre-installed. The only required initialisation step is `CREATE EXTENSION IF NOT EXISTS vector`, which `PGVectorStore.from_params()` handles automatically on first connection.

---

## 6. Interrupt / Resume Lifecycle

The mechanism that enables multi-turn tool interactions is LangGraph's `interrupt()` primitive combined with the checkpointer.

### 6.1 How interrupt() works

`interrupt(value)` raises a special internal exception that unwinds the current node cleanly. LangGraph catches it, writes the full state to the checkpointer keyed by `thread_id`, and marks the graph as suspended at that node. The `value` passed to `interrupt()` is surfaced as the interrupt payload — your code uses it as the prompt text to send to the user.

When the next user message arrives with the same session ID, the invoker calls `graph.ainvoke(Command(resume=user_message), config=config)`. LangGraph loads the checkpoint, restores the exact node and state, and resumes Python execution at the line immediately after the `interrupt()` call. The return value of `interrupt()` is the user's answer.

> **Key insight:** The tool node does not split its logic across two separate nodes with a conditional edge between them. Ask and validate live in one function. This makes multi-step tool logic dramatically easier to read and reason about.

### 6.2 FastAPI routing logic

FastAPI needs to distinguish between a fresh turn and a continuation of a suspended tool. This is done by inspecting the checkpoint before invoking the graph:

```python
# api/routes/chat.py

@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    config = {"configurable": {"thread_id": req.session_id}}
    state  = await graph.aget_state(config)

    if state and state.next:
        # Graph is suspended — this message resumes a tool
        input_ = Command(resume=req.message)
    else:
        # Fresh turn — normal invocation
        input_ = {"messages": [HumanMessage(content=req.message)]}

    return StreamingResponse(
        stream_graph_events(graph, input_, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### 6.3 Off-topic message handling

When a tool is mid-flow, the user may send an off-topic message instead of the expected answer. The recommended default behaviour is **strict mode**: the incoming message is treated as the tool answer regardless of content. The tool's validation logic inside the node is responsible for detecting invalid answers and re-prompting.

An escape hatch is provided via a reserved command prefix. If the message starts with `/cancel`, FastAPI clears the suspended state for that session:

```python
if req.message.strip().lower().startswith("/cancel"):
    await graph.aupdate_state(
        config,
        {"active_tool": None, "tool_status": "idle"},
        as_node="output_formatter",
    )
    # stream a cancellation acknowledgement and return
```

---

## 7. SSE Event Protocol

Every event streamed from the backend to the frontend follows the same envelope. The frontend never needs to parse free-form text to understand the conversation state.

### 7.1 Envelope structure

```json
{
  "type":    "<event_type>",
  "payload": {},
  "meta": {
    "session_id":  "<str>",
    "active_tool": "<tool_name> | null",
    "tool_step":   "<int> | null",
    "tool_total":  "<int> | null",
    "resumable":   "<bool>",
    "can_escape":  "<bool>"
  }
}
```

`resumable: true` means the graph is suspended and the next `POST /api/chat` will resume a tool rather than start a fresh turn. The frontend uses this to know whether to show the standard chat input or a tool-specific input control.

### 7.2 Event type reference

| type | When emitted | Key payload fields | Frontend action |
|---|---|---|---|
| `session_state` | First event of every turn, before any content | `active_tool`, `resumable` | Update UI mode, show/hide tool chrome |
| `text_delta` | Each streaming LLM token | `token: str` | Append to chat bubble |
| `text_done` | LLM stream complete | `full_text: str` | Finalise bubble |
| `tool_start` | Tool graph begins executing | `tool_name`, `total_steps` | Show progress bar and cancel button |
| `tool_question` | `interrupt()` reached inside tool | `text`, `step`, `input_type` | Render question, optionally constrain input |
| `tool_progress` | One step completed | `step`, `total` | Advance progress indicator |
| `tool_complete` | Tool graph reached END | `payload` (tool output) | Clear tool chrome, show result |
| `error` | Any unhandled exception | `message`, `recoverable` | Show error state |

### 7.3 input_type values on tool_question

The `input_type` field on `tool_question` events lets the frontend render the appropriate input control without knowing anything about the specific tool:

| input_type | Frontend renders |
|---|---|
| `free_text` | Standard chat input (default) |
| `choice` | Button group — `options` array in payload |
| `number` | Numeric input with optional `min` / `max` |
| `date` | Date picker |
| `confirm` | Yes / No buttons |

### 7.4 Streaming implementation

```python
# api/streaming.py

import json
from typing import AsyncIterator

async def stream_graph_events(
    graph, input_, config: dict
) -> AsyncIterator[str]:

    state     = await graph.aget_state(config)
    base_meta = build_meta(config, state)

    yield sse("session_state", {}, base_meta)

    async for event in graph.astream_events(input_, config=config, version="v2"):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            token = event["data"]["chunk"].content
            if token:
                yield sse("text_delta", {"token": token}, base_meta)

        elif kind == "on_custom_event":
            name = event["name"]
            data = event["data"]

            if name == "tool_start":
                yield sse("tool_start", data, {
                    **base_meta,
                    "active_tool": data["tool_name"],
                    "tool_total":  data.get("total_steps"),
                })

            elif name == "tool_question":
                yield sse("tool_question", data, {
                    **base_meta,
                    "resumable":  True,
                    "can_escape": True,
                    "tool_step":  data["step"],
                })

            elif name in ("tool_progress", "tool_complete"):
                yield sse(name, data, base_meta)

        elif kind == "on_chain_error":
            yield sse("error", {
                "message":     str(event["data"]["error"]),
                "recoverable": False,
            }, base_meta)


def sse(type_: str, payload: dict, meta: dict) -> str:
    return f"data: {json.dumps({'type': type_, 'payload': payload, 'meta': meta})}\n\n"
```

---

## 8. LLM Gateway — LiteLLM

All LLM calls at every layer — the intent router, the fallback chat node, tool graph synthesis steps — go through a single LiteLLM wrapper. This provides one place to configure model routing, fallbacks, rate limits, and cost tracking.

```python
# engine/llm.py

from litellm import acompletion
import os

async def llm(messages: list[dict], stream=True, **kwargs):
    return await acompletion(
        model    = os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        messages = messages,
        stream   = stream,
        **kwargs,
    )

# Swap model without touching any graph code:
# LLM_MODEL=claude-sonnet-4-6          → Anthropic
# LLM_MODEL=ollama/llama3              → local Ollama
# LLM_MODEL=openai/gpt-4o             → OpenAI
```

The intent router uses a separate, cheaper model by default (configurable via `ROUTER_MODEL`) since classification is a lightweight task. Tool graphs that need stronger reasoning can request a different model via the `llm()` kwargs.

---

## 9. RAG Tool — LlamaIndex + pgvector Integration

Retrieval-augmented generation is implemented entirely as a Layer 3 tool graph. LlamaIndex is encapsulated inside `rag_tool.py` and has no dependency touching Layer 1 or Layer 2. The vector store is a `PGVectorStore` backed by the same PostgreSQL instance used for checkpointing — no separate service required.

```python
# backend/tools/rag/tool.py

from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.postgres import PGVectorStore

class RAGTool:
    name = "rag"

    def __init__(self, vector_store: PGVectorStore,
                 top_k: int = 5,
                 rerank: bool = True):
        self._index  = VectorStoreIndex.from_vector_store(vector_store)
        self._top_k  = top_k
        self._rerank = rerank

    def describe(self) -> str:
        return "Retrieves relevant documents and synthesises a grounded answer."

    def build(self) -> CompiledGraph:
        async def retrieve_and_synthesise(state: ToolState):
            query = state["messages"][-1].content

            # 1. Optional query rewrite (HyDE or step-back)
            rewritten = await rewrite_query(query)

            # 2. Retrieve from pgvector
            retriever = self._index.as_retriever(similarity_top_k=self._top_k)
            nodes     = await retriever.aretrieve(rewritten)

            # 3. Optional re-rank
            if self._rerank:
                nodes = await rerank(nodes, query)

            # 4. Synthesise via LiteLLM
            context = "\n---\n".join(n.text for n in nodes)
            answer  = await llm([
                {"role": "system", "content": RAG_SYSTEM_PROMPT},
                {"role": "user",   "content": f"Context:\n{context}\n\nQuestion: {query}"},
            ])

            return {
                **state,
                "tool_output": {
                    "answer":  answer,
                    "sources": [n.metadata for n in nodes],
                },
                "is_complete": True,
            }

        g = StateGraph(ToolState)
        g.add_node("retrieve", retrieve_and_synthesise)
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", END)
        return g.compile()
```

The RAG chatbot use case — the simplest possible deployment — is a single subgraph containing only this tool:

```python
class RAGChatbotSubgraph:
    name = "rag_chatbot"

    def describe(self) -> str:
        return "Answer questions by searching the knowledge base."

    def build(self) -> CompiledGraph:
        g = StateGraph(SubgraphState)
        g.add_node("rag", self._rag_tool.build())
        g.add_edge(START, "rag")
        g.add_edge("rag", END)
        return g.compile()
```

---

## 10. Project Structure

```
chatbot-framework/
│
├── backend/                         # Backend container (FastAPI + LangGraph engine)
│   │
│   ├── core/                        #   Layer 1 — never modified
│   │   ├── graph.py                 #     build_core_graph()
│   │   ├── nodes/                   #     session_manager, intent_router,
│   │   │                            #     fallback_llm, output_formatter
│   │   ├── state.py                 #     CoreState, SubgraphState, ToolState
│   │   ├── protocols.py             #     SubgraphProtocol, ToolProtocol
│   │   └── registry.py              #     SubgraphRegistry
│   │
│   ├── tools/                       #   Layer 3 — reusable tool graphs
│   │   ├── data_collector/
│   │   │   └── tool.py              #     DataCollectorTool
│   │   ├── rag/
│   │   │   └── tool.py              #     RAGTool
│   │   ├── analyzer/
│   │   │   └── tool.py              #     AnalyzerTool
│   │   └── presenter/
│   │       └── tool.py              #     PresenterTool
│   │
│   ├── apps/                        #   Layer 2 — use-case subgraphs (app-owned)
│   │   ├── assessment/
│   │   │   └── subgraph.py          #     AssessmentSubgraph
│   │   └── rag_chatbot/
│   │       └── subgraph.py          #     RAGChatbotSubgraph
│   │
│   ├── api/                         #   FastAPI entry point
│   │   ├── main.py                  #     app startup, subgraph registration
│   │   ├── routes/
│   │   │   └── chat.py              #     POST /api/chat
│   │   ├── streaming.py             #     stream_graph_events(), sse()
│   │   └── models.py                #     ChatRequest, ChatResponse Pydantic models
│   │
│   ├── engine/                      #   LangGraph engine helpers
│   │   ├── checkpointer.py          #     AsyncPostgresSaver setup
│   │   ├── vector_store.py          #     PGVectorStore setup
│   │   └── llm.py                   #     LiteLLM wrapper
│   │
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                        # Frontend container (React / Vue)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWindow.vue
│   │   │   ├── ToolChrome.vue       #   progress bar, step counter, cancel
│   │   │   └── QuestionInput.vue
│   │   ├── composables/
│   │   │   └── useChat.ts           #   SSE event handler + UI state machine
│   │   └── types/
│   │       └── events.ts            #   typed SSE envelope
│   ├── package.json
│   └── Dockerfile
│
├── data/                            # Persistent volumes (gitignored)
│   └── postgres/                    #   PostgreSQL data — checkpoints + pgvector embeddings
│
└── docker-compose.yml
```

---

## 11. Docker Compose

```yaml
# docker-compose.yml

services:

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://backend:8000
    depends_on: [backend]

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - LLM_MODEL=gpt-4o-mini
      - ROUTER_MODEL=gpt-4o-mini
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: pgvector/pgvector:pg16   # official pgvector image — extension pre-installed
    expose:
      - "5432"                      # not public — only reachable from backend
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

> **Single Postgres for everything:** The `pgvector/pgvector:pg16` image ships with the `vector` extension pre-installed. LangGraph's `AsyncPostgresSaver.setup()` creates its checkpoint tables on first startup. LlamaIndex's `PGVectorStore.from_params()` creates the embeddings table automatically. No manual SQL migration needed. The `healthcheck` ensures the backend only starts once Postgres is ready to accept connections.

---

## 12. Application Startup & Registration

The application is assembled in `api/main.py`. Subgraphs are instantiated, injected with their tool dependencies, and registered into the core graph in one place. Adding a new use case means adding lines here — nothing else changes.

```python
# backend/api/main.py

from fastapi import FastAPI
from core.registry        import SubgraphRegistry
from core.graph           import build_core_graph
from engine.checkpointer  import get_checkpointer
from engine.vector_store  import get_vector_store

# Tools
from tools.data_collector.tool import DataCollectorTool
from tools.analyzer.tool       import AnalyzerTool
from tools.presenter.tool      import PresenterTool
from tools.rag.tool            import RAGTool

# Use-case subgraphs
from apps.assessment.subgraph  import AssessmentSubgraph
from apps.rag_chatbot.subgraph import RAGChatbotSubgraph

app = FastAPI()

@app.on_event("startup")
async def startup():
    # Instantiate tools
    collector = DataCollectorTool(questions=[
        "What is your full name?",
        "How old are you?",
        "What is your primary goal?",
    ])
    analyzer  = AnalyzerTool(scoring_fn=score_assessment)
    presenter = PresenterTool()
    rag_tool  = RAGTool(vector_store=get_vector_store(), top_k=5)

    # Instantiate and register subgraphs
    registry = SubgraphRegistry()
    registry.register(AssessmentSubgraph(collector, analyzer, presenter))
    registry.register(RAGChatbotSubgraph(rag_tool))

    # Build and store the compiled graph
    checkpointer    = await get_checkpointer()
    app.state.graph = build_core_graph(registry).compile(
        checkpointer=checkpointer
    )

from api.routes.chat import router
app.include_router(router, prefix="/api")
```

---

## 13. Frontend — UI State Machine

The frontend maintains a simple state machine driven by the SSE event stream. The state determines which UI components are rendered.

| UI state | Entered when | Components visible |
|---|---|---|
| `idle` | `session_state` with `resumable=false` and no `active_tool` | Chat input enabled, no tool chrome |
| `streaming` | `text_delta` received | Streaming chat bubble, input disabled |
| `tool_active` | `tool_start` received | Progress bar, tool name, cancel button |
| `awaiting_input` | `tool_question` received | Question text, input control (type from `input_type`), send button |
| `error` | `error` event received | Error message, retry / restart options |

```typescript
// frontend/src/composables/useChat.ts

type UIState = "idle" | "streaming" | "tool_active" | "awaiting_input" | "error"

export function useChat(sessionId: string) {
  const uiState  = ref<UIState>("idle")
  const messages = ref<Message[]>([])
  const toolMeta = ref<ToolMeta | null>(null)
  const currentQ = ref<QuestionEvent | null>(null)

  async function send(text: string) {
    const res = await fetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, session_id: sessionId }),
    })
    const reader  = res.body!.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const lines = decoder.decode(value).split("\n")
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        const event = JSON.parse(line.slice(6))
        handleEvent(event)
      }
    }
  }

  function handleEvent(event: SSEEvent) {
    switch (event.type) {
      case "session_state":
        uiState.value = event.meta.resumable ? "awaiting_input" : "idle"
        break
      case "text_delta":
        uiState.value = "streaming"
        appendToken(event.payload.token)
        break
      case "tool_start":
        uiState.value = "tool_active"
        toolMeta.value = {
          name:  event.meta.active_tool,
          total: event.meta.tool_total,
          step:  0,
        }
        break
      case "tool_question":
        uiState.value  = "awaiting_input"
        currentQ.value = event.payload
        if (toolMeta.value) toolMeta.value.step = event.meta.tool_step!
        break
      case "tool_progress":
        if (toolMeta.value) toolMeta.value.step = event.payload.step
        break
      case "tool_complete":
        uiState.value  = "idle"
        toolMeta.value = null
        currentQ.value = null
        break
      case "error":
        uiState.value = "error"
        break
    }
  }

  return { uiState, messages, toolMeta, currentQ, send }
}
```

---

## 14. Extending the Framework

Adding a new use case follows a fixed three-step pattern. No existing file is modified.

### Step 1 — Write your tool graphs (if needed)

Create `tools/my_tool/tool.py`. Implement `ToolProtocol`. Use `interrupt()` for any step that needs user input. Emit `tool_start`, `tool_question`, `tool_progress`, `tool_complete` events via `adispatch_custom_event`.

### Step 2 — Write your subgraph

Create `apps/my_use_case/subgraph.py`. Implement `SubgraphProtocol`. Compose your tools as nodes. Write a clear `describe()` string — this is what the intent router reads to decide when to dispatch to your subgraph.

### Step 3 — Register at startup

In `api/main.py`, instantiate your tools and subgraph, and call `registry.register(MySubgraph(...))`. Restart the engine. The intent router now knows about your new use case.

> **Nothing else changes.** The core graph, the SSE streaming layer, the checkpointer, the frontend state machine — none of it needs to be touched. The framework treats your new subgraph identically to the built-in ones.

---

## 15. Decision Log

| Decision | Alternative considered | Reason chosen |
|---|---|---|
| PostgreSQL + pgvector | Redis + Qdrant (two separate services) | Single database for both conversation checkpoints and vector embeddings. One container, one volume, one backup strategy, one connection string. Scales horizontally via standard Postgres replication. |
| `interrupt()` in a single node | Separate ask/validate nodes with conditional edge | Keeps multi-step logic readable in one function. The loop structure is explicit in code, not scattered across graph edges. |
| Typed SSE envelope | Plain text stream | Frontend can drive a proper UI state machine without parsing content. Tool authors can add new event types without frontend changes. |
| LiteLLM as gateway | Direct OpenAI / Anthropic SDKs | Model swap is a single env var. Fallback chains and cost tracking configured in one place. |
| LlamaIndex inside tool only | LlamaIndex at subgraph or core level | Retrieval implementation is completely isolated. Swap vector stores, add re-ranking, change chunking — zero changes outside the tool. |
| `describe()` for intent routing | Manual routing table / enum | Adding a subgraph automatically makes the router aware. No registration step beyond `registry.register()`. |
| Tool state via TypedDict inheritance | Separate state objects passed as function args | Full state is always available throughout the graph. Checkpointing is automatic. |

---

## 16. Production Upgrade Path

The framework is designed so that scaling concerns are addressed by swapping single components, not redesigning the architecture:

- **Horizontal scaling:** PostgreSQL handles multiple concurrent backend instances natively — all instances share the same checkpoint and vector store. Add read replicas for query-heavy RAG workloads, or drop PgBouncer in front of the database for connection pooling at high concurrency. No application code changes.

- **Model upgrade:** Set `LLM_MODEL=claude-opus-4-6` or any LiteLLM-supported model string. No code changes.

- **Embedding model swap:** Change the `embed_dim` parameter in `get_vector_store()` and re-index your documents. The `PGVectorStore` table is recreated automatically. No other code changes.

- **Auth:** Add authentication middleware to FastAPI. The session ID becomes a verified user ID. The graph state already carries `metadata` for user context.

- **Observability:** LiteLLM has built-in logging callbacks. LangGraph supports LangSmith tracing. Both require only configuration, no code changes.

---

*Universal Chatbot Framework — Architecture Proposal v1.0*