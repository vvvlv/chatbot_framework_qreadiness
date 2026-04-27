# QReadiness Chatbot Architecture

This document describes the current architecture of the `qreadiness_chatbot` project after the recent deployment and infrastructure updates.

## 1) High-Level Overview

The system follows a **Shell-and-Core** design:

- **Shell (FastAPI + Core Graph):** Handles API I/O, streaming, session continuity, routing, and persistence wiring.
- **Core (Use-Case Subgraph):** The `quantum_readiness` subgraph handles the domain workflow.
- **Frontend (Next.js):** A thin UI layer that sends user messages and renders streamed Server-Sent Events (SSE).
- **Infrastructure (Docker):** Three compose profiles support local full-stack, infra-only, and VM/reverse-proxy deployment.

## 2) Runtime Components

### Backend API (FastAPI)

Backend entrypoint: `backend/api/main.py`

Responsibilities:

- Initializes FastAPI and CORS (`ALLOWED_ORIGINS` from env).
- Instantiates shared services:
  - model gateway (`core/llm.py` and `core/model_gateway.py` via LiteLLM)
  - common tools registry (`Interrupt_tool`, `RAG_tool`)
  - subgraph registry (`QuantumReadinessSubgraph`)
- Builds and stores the compiled LangGraph in `app.state.graph`.
- Initializes `InteractionLogger` in `app.state.interaction_logger`.
- Exposes `/health` and chat routes under `/api`.

### Chat Transport and Streaming

Main route: `backend/api/routes/chat.py`  
Streaming adapter: `backend/api/streaming.py`

Flow:

1. Frontend posts to `POST /api/chat` with:
   - `message`
   - `session_id` (UUID thread key)
   - optional `prompt_id` (for safe resume)
2. Route applies:
   - request rate limiting (IP + hashed session bucket)
   - resume payload size guard
   - suspended state checks using `graph.aget_state(...)`
3. Route chooses input mode:
   - new turn: LangGraph state input with `HumanMessage`
   - resume turn: `Command(resume=...)`
4. Route returns `StreamingResponse` (`text/event-stream`) from `stream_graph_events`.

SSE events include:

- `session_state`
- `text_delta`
- `text_done`
- `tool_start`
- `tool_question`
- `tool_progress`
- `tool_complete`
- `tool_waiting_input`
- `error`

This enables interrupt/resume conversational workflows without polling.

### Graph Orchestration (LangGraph)

Core graph builder: `backend/core/graph.py`

Fixed Layer-1 nodes:

1. `session_manager`
2. `intent_router`
3. `fallback_llm`
4. `output_formatter`

Dynamic behavior:

- Registered subgraphs are added as nodes at startup.
- Conditional routing from `intent_router` sends execution to:
  - matched subgraph (`active_subgraph`), or
  - `fallback_llm` for general chat.
- Every route ends at `output_formatter`, then `END`.

### Quantum Readiness Use-Case Subgraph

Subgraph definition: `backend/apps/quantum_readiness/maingraph.py`

The `quantum_readiness` workflow composes three tool nodes:

1. `data_collector` (interactive information gathering)
2. `analyzer` (assessment and score/archetype logic)
3. `presenter` (final explanation/report generation)

Execution path:

- `START -> data_collector`
- conditional:
  - continue to `analyzer`, or
  - finish early (`END`) when needed
- `analyzer -> presenter -> END`

### State Persistence and Session Continuity

Checkpointer factory: `backend/core/checkpointer.py`

- Uses `AsyncPostgresSaver` when `DATABASE_URL` is available.
- Falls back to `InMemorySaver` in development if Postgres saver is unavailable.
- Enforces persistent mode in production (`ENV=prod` requires DB-backed checkpointer).

Session model:

- Frontend generates/provides `session_id`.
- Backend maps it to LangGraph `thread_id` in `config`.
- Thread state supports resume after tool interrupts (`pending_prompt_id` validation included).

### Observability

- Runtime interaction events are persisted through `InteractionLogger`.
- Lightweight debug endpoint:
  - `GET /api/debug/interactions?limit=...&session_id=...`

## 3) Frontend Architecture (Next.js App Router)

Main page: `frontend/app/page.tsx`  
State/transport hook: `frontend/app/hooks/useChat.ts`

Frontend principles:

- No model calls from browser.
- All AI logic stays on backend graph/tool nodes.
- UI is event-driven by SSE messages from backend.

`useChat` hook responsibilities:

- Maintains UI state machine (`idle`, `streaming`, `tool_active`, `awaiting_input`, `error`).
- Sends user input to backend `POST /api/chat`.
- Parses SSE stream line-by-line.
- Appends assistant/user messages.
- Tracks interactive prompt metadata (`prompt_id`) for resume safety.
- Supports user cancellation by issuing `/cancel`.

## 4) Deployment and Compose Topology

The project now supports three compose entry points.

### `docker-compose.infra.yml` (infra only)

Services:

- `postgres` (pgvector image)
- `litellm`

Use this when backend/frontend run outside Docker but still need shared infra.

### `docker-compose.yml` (full local stack)

Services:

- `postgres`
- `litellm`
- `backend` (FastAPI)
- `frontend` (Next.js)
- `pgadmin` (optional admin UI)

Current local defaults:

- backend exposed on `8002`
- frontend exposed on `3001`
- pgadmin on `5051`

### `docker-compose.vm.yml` (VM / reverse-proxy profile)

VM-oriented service names and network layout:

- Internal app network: `qreadiness_chatbot_internal`
- External reverse-proxy network: `caddy` (external)

Ports and runtime commands:

- backend runs on `8005` (`uvicorn ... --port 8005`)
- frontend runs on `3005` (`npm run start -- -p 3005`)
- postgres exposed on host `5542`
- pgadmin moved to `5050` and enabled through `debug` profile

This compose file is intended for deployments where a reverse proxy (e.g., Caddy) routes public traffic to the internal containers.

## 5) Data Flow (End-to-End)

1. User enters text in frontend chat UI.
2. Frontend posts JSON to backend `/api/chat`.
3. Backend executes core graph:
   - session pre-processing
   - intent routing
   - subgraph/fallback execution
   - output formatting
4. Backend streams typed SSE events during execution.
5. Frontend incrementally renders:
   - token deltas
   - tool progress/questions
   - final text output
6. If interrupted, backend stores checkpoint and frontend resumes with `prompt_id`.

## 6) Key Environment Variables

- `DATABASE_URL`: LangGraph checkpoint persistence target.
- `INTERACTION_LOG_DB_URL`: interaction event persistence target.
- `ALLOWED_ORIGINS`: CORS allowlist for frontend hosts.
- `NEXT_PUBLIC_API_URL` (frontend build/runtime): backend base URL.
- `ENV`: affects strict persistence behavior (`prod` vs `dev`).

## 7) Current Architectural Characteristics

- Fully async backend request/stream processing.
- Streaming-first UX with SSE envelopes.
- Tool-based, resumable stateful workflows via LangGraph checkpoints.
- Clear separation of concerns between transport shell and use-case core graph.
- Multiple Docker run modes for local development and VM deployment.
