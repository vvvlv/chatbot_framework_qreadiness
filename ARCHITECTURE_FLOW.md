# Universal Chatbot Framework: Architecture & Execution Flow

This document explains how the backend is structured and how a user message turns into streamed responses, including multi-turn tool workflows using `interrupt()` / resume.

## 1. Folder Structure (Backend)

`qreadiness_chatbot/backend/` follows the “Shell-and-Core” pattern and a strict 3-layer LangGraph hierarchy:

- `backend/core/` (Layer 1, platform-owned)
  - Core graph builder (`graph.py`)
  - Core nodes:
    - `session_manager` (trim history, set metadata)
    - `intent_router` (classify which subgraph to run)
    - `fallback_llm` (plain conversational response)
    - `output_formatter` (normalize final output)
- `backend/apps/` (Layer 2, app-owned use-case subgraphs)
  - Each subgraph orchestrates tool execution order and branching
  - Example: `apps/quantum_readiness/subgraph.py`
- `backend/tools/` (Layer 3, tool-owned reusable interaction patterns)
  - Each tool is a compiled LangGraph subgraph implementing one reusable pattern
  - Example: `tools/quantum_data_collector/tool.py` uses `interrupt()` to ask user questions step-by-step
- `backend/api/` (FastAPI shell)
  - Routes and SSE streaming adapter
  - Example: `api/routes/chat.py`, `api/streaming.py`, `api/models.py`
- Infra helpers live inside `backend/core/`:
  - `core/llm.py` (LiteLLM routing via `core/model_gateway.py`)
  - `core/checkpointer.py` (LangGraph AsyncPostgresSaver / InMemory)
  - `core/vector_store.py` (PGVectorStore setup placeholder)

Tool-level RAG interfaces live with tools:
- `tools/rag/retriever_base.py`

## 2. State Ownership (Why Resume Works)

The graph state is represented as a TypedDict hierarchy:

- `CoreState` (Layer 1 owned fields)
  - `messages`, `output`
  - `intent`, `active_subgraph`, `subgraph_status`
  - `metadata`
- `SubgraphState` (Layer 2 owned fields)
  - `active_tool`, `tool_status`, `tool_input`, `tool_output`
- `ToolState` (Layer 3 owned fields)
  - `step`, `step_data`, `is_complete`, `error`

Ownership rule: a layer can only write to fields it owns (or below it).

Checkpointing/resume relies on LangGraph restoring the full state for the active tool/subgraph based on `thread_id` (your frontend session id).

## 3. End-to-End Request Flow

### 3.1 HTTP entrypoint

- Frontend sends `POST /api/chat` with:
  - `message` (user text)
  - `session_id` (UUID / thread id)
- Backend sets `config = {"configurable": {"thread_id": session_id}}`
- Backend fetches graph suspension status using `graph.aget_state(config)`

### 3.2 Fresh turn vs resume

Backend decides between:

- Fresh turn
  - Input: `{"messages": [HumanMessage(content=req.message)]}`
- Resume turn (graph suspended at a tool `interrupt()`)
  - Input: `Command(resume=req.message)`

### 3.3 SSE streaming

Backend returns `StreamingResponse(..., media_type="text/event-stream")`

`api/streaming.py` wraps LangGraph’s `graph.astream_events(...)` and emits a typed SSE envelope:

- `session_state` first event of every turn (sets `resumable`, `active_tool`, etc.)
- `text_delta` for streaming LLM tokens (when applicable)
- `tool_start`, `tool_question`, `tool_progress`, `tool_complete` for tool workflows
- `error` for failures

## 4. Core Graph Flow (Layer 1)

The compiled core graph is structured as:

1. `session_manager`
   - Trims conversation history
   - Ensures metadata exists
2. `intent_router`
   - Reads all registered subgraphs and their `describe()` strings
   - Classifies intent via LiteLLM
   - Sets `active_subgraph` / `intent`
3. Conditional routing
   - If `active_subgraph` matches a registered Layer 2 subgraph, dispatch to it
   - Otherwise route to `fallback_llm`
4. `output_formatter`
   - Normalizes the final output and prepares it for SSE completion

## 5. Use-case Subgraph Flow (Layer 2)

A subgraph defines orchestration only:

- It composes tool graphs as nodes
- It sets branching/ordering between tools
- It does not implement tool internals

Example: `QuantumReadinessSubgraph` orchestrates:

- `quantum_data_collector` → `quantum_analyzer` → `quantum_presenter`

Each tool emits custom events (tool chrome + questions + progress).

## 6. Tool Flow (Layer 3) with `interrupt()` / Resume

Tools implement stepwise interaction patterns:

1. Tool emits `tool_start`
2. Tool emits `tool_question` and calls `interrupt(question_text)`
   - LangGraph suspends execution and checkpoints state keyed by `thread_id`
   - The HTTP response ends after streaming the interrupt question to the frontend
3. Next user message arrives
   - FastAPI detects the suspended graph and calls:
     - `graph.astream_events(Command(resume=user_message), ...)`
4. LangGraph restores the checkpoint and continues right after `interrupt(...)`

### Important note about step counting

Tool “step” (for progress and UI) should reflect meaningful user prompts.
Clarification prompts are handled so they do not inflate the global `total_steps` unexpectedly.

## 7. SSE Event-to-UI Mapping (Conceptual)

The frontend can drive a UI state machine from the streamed envelopes:

- `resumable=true` → show tool input instead of normal chat input
- `tool_question` → render tool-specific question UI
- `tool_progress` → update progress indicator
- `tool_complete` / `text_done` → return to normal chat mode

## 8. Extending the Framework

To add a new use case:

1. Add tools (optional): `backend/tools/<tool_name>/tool.py`
2. Add a subgraph: `backend/apps/<use_case>/subgraph.py`
   - Must implement `name`, `describe()`, and `build()`
3. Register at startup in `backend/api/main.py`
   - The intent router automatically learns subgraphs from their `describe()` output

