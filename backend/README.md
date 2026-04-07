# Quantum Readiness Chatbot - Backend

Backend implementation of the Quantum Readiness assessment app using a 3-layer shell-and-core architecture.

## System Architecture

The backend is organized into three layers:

- **Layer 1: Core (`core/`)**
Platform-owned shell graph and shared infrastructure:
  - session handling
  - intent routing
  - fallback conversational response
  - output formatting
  - checkpointer and model gateway wiring
- **Layer 2: App Subgraphs (`apps/`)**
Use-case orchestration graphs.
`apps/quantum_readiness/subgraph.py` coordinates collector -> analyzer -> presenter with explicit state handoff nodes.
- **Layer 3: Tools (`tools/`)**
Domain logic encapsulated as tools:
  - `quantum_data_collector` (multi-turn assessment with interrupt/resume, prompt ids, validation, clarification, retry caps)
  - `quantum_analyzer` (scoring, archetype mapping, risk/opportunity breakdowns)
  - `quantum_presenter` (final report assembly and narrative)
  - `tools/rag` shared retriever interfaces used by tools

## Current Folder Structure

```
backend/
├── api/
│   ├── main.py                # FastAPI app startup and graph wiring
│   ├── models.py              # Pydantic request/response models
│   ├── routes/
│   │   └── chat.py            # POST /api/chat
│   └── streaming.py           # SSE event envelope and stream adapter
├── apps/
│   └── quantum_readiness/
│       └── subgraph.py        # App-level orchestration graph
├── core/
│   ├── __init__.py
│   ├── checkpointer.py        # InMemorySaver / AsyncPostgresSaver setup
│   ├── graph.py               # Core shell graph builder
│   ├── llm.py                 # Simple LLM helper over model gateway
│   ├── model_gateway.py       # LiteLLM-backed model abstraction
│   ├── nodes/                 # session_manager, intent_router, fallback_llm, output_formatter
│   ├── protocols.py           # SubgraphProtocol, ToolProtocol
│   ├── registry.py            # SubgraphRegistry
│   ├── state.py               # CoreState, SubgraphState, ToolState
│   └── vector_store.py        # Vector store scaffold (pgvector target)
└── tools/
    ├── quantum_analyzer/
    ├── quantum_data_collector/
    ├── quantum_presenter/
    └── rag/
        └── retriever_base.py
```

Note: legacy `runtime/`, `engine/`, and `services/` directories were removed; their responsibilities now live in `core/` and `tools/`.

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

1. Create `.env` from `env.example` and fill your key:

```bash
cp env.example .env
```

Then set environment variables in `.env`:

```env
# LLM Configuration
LLM_MODEL=mistral/mistral-small-latest
MISTRAL_API_KEY=your_key_here

# Runtime and API security
ENV=dev
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_REQUESTS_PER_WINDOW=45
MAX_RESUME_BYTES=8000

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/chatbot
```

1. Run the server:

```bash
uvicorn api.main:app --reload --port 8000
```

## API Endpoints

### `POST /api/chat`

Chat endpoint with SSE streaming and interrupt/resume support.

**Request:**

```json
{
  "message": "I want to assess my quantum readiness",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "prompt_id": "optional-when-resuming"
}
```

**Response:** Server-Sent Events (SSE) stream with typed events:

- `session_state` - Initial state
- `text_delta` - Streaming LLM tokens
- `tool_start` - Tool begins execution
- `tool_question` - Tool asks a question (graph pauses via `interrupt()`)
- `tool_waiting_input` - Graph is suspended and waiting for user input
- `tool_progress` - Tool step completed
- `tool_complete` - Tool finished
- `text_done` - Final response
- `error` - Error occurred

### `GET /health`

Health check endpoint.

## How The App Works (Runtime Flow)

1. **Request enters FastAPI**
  `POST /api/chat` accepts `message` and `session_id`.
2. **Session-aware graph execution**
  The API checks if the session has a suspended graph state:
  - new session -> normal invoke
  - suspended session -> resume with `Command(resume={text, prompt_id})`
  - stale resume prompt ids are rejected
3. **Core routing**
  The core shell graph runs session manager + intent router and dispatches to `quantum_readiness` when assessment intent is detected.
4. **Collector phase (multi-turn)**
  `QuantumDataCollectorTool` asks one question at a time using `interrupt()`.
   Behavior includes:
  - strict per-field validation
  - answer normalization/rewriting
  - clarification questions when needed
  - bounded step progress (`total_steps=4` in current prototype)
  - slash commands (`/skip`, `/clarify`, `/cancel`)
  - prompt id replay/stale protection on resume
  - graceful low-confidence fallback after retry cap
5. **Analyzer phase**
  `QuantumAnalyzerTool` consumes collector output and computes:
  - readiness score
  - archetype
  - risk and opportunity breakdown
  - unknown/low-confidence dimensions
6. **Presenter phase**
  `QuantumPresenterTool` produces a structured final report and optional benchmark context through the RAG interface.
7. **Streaming to frontend**
  `api/streaming.py` emits typed SSE events throughout execution, including tool events and final text output.

## Key Features

- **Interrupt/resume conversations**: reliable multi-turn flow with LangGraph checkpointing
- **SSE-first API**: typed streaming events for responsive UI rendering
- **Resume hardening**: prompt-id matching guards stale/replayed resume payloads
- **Strong validation loop**: gibberish/off-topic rejection plus clarification retries
- **Meaningful unknown handling**: uncertain answers can be captured as low confidence instead of stalling
- **Structured scoring output**: score + archetype + granular breakdowns
- **RAG-ready presenter layer**: retriever interface in `tools/rag/retriever_base.py`

## Development

The system is designed for extensibility:

- **Add a new use case**: create a subgraph under `apps/` and register it in `api/main.py`
- **Add a new tool**: create it under `tools/` and implement `ToolProtocol`
- **Keep frontend dumb**: no prompt logic client-side; backend owns orchestration
- **Keep model calls centralized**: route through `core/model_gateway.py`

