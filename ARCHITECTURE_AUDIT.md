# Architecture Audit: What Is Wrong and How to Fix It

This codebase has a strong Shell-and-Core direction, but the current implementation is still a prototype and has several architecture gaps that will cause reliability, scalability, and maintainability issues in production.

## 1) Critical gaps

1. **Persistence is not production-safe by default**
  - `backend/core/checkpointer.py` silently falls back to `InMemorySaver`.
  - Result: interrupt/resume state is lost on restart, so multi-step workflows are fragile.
  - **Fix:** make Postgres checkpointer mandatory outside local dev; fail startup if unavailable.
2. **Data layer is partially stubbed**
  - `backend/core/vector_store.py` returns `None`.
  - `backend/api/main.py` wires `DummyRetriever` instead of LlamaIndex + pgvector hybrid retrieval/reranking.
  - Result: RAG quality and architecture claims do not match runtime behavior.
  - **Fix:** implement a real pgvector-backed retriever adapter and swap out `DummyRetriever`.
3. **No containerization baseline**
  - No `Dockerfile` and no `docker-compose*.yml`.
  - Result: architecture cannot be reproduced consistently across environments and violates docker-native requirement.
  - **Fix:** add `docker-compose.infra.yml` (Postgres/pgvector/LiteLLM), backend and frontend Dockerfiles, and app-level compose for local orchestration.

## 2) High-priority design risks

1. **State layering is conceptually clean but technically over-coupled**
  - `backend/core/graph.py` compiles top-level with `ToolState` instead of `CoreState`.
  - Result: Layer 1 depends on Layer 3 fields, weakening ownership boundaries.
  - **Fix:** keep top-level graph state minimal (`CoreState`) and pass tool-specific payloads via explicit scoped fields/interfaces.
2. **Frontend bypasses Vercel AI SDK integration pattern**
  - `frontend/app/hooks/useChat.ts` manually parses SSE; `ai` package is installed but not used.
  - Result: duplicated stream handling logic and higher UI maintenance cost.
  - **Fix:** migrate to Vercel AI SDK stream primitives (`useChat`/transport adaptation) while keeping backend as the orchestration source.
3. **Session/thread identity is weak**
  - `frontend/app/components/ChatWindow.tsx` uses `session-${Date.now()}`.
  - Result: non-UUID IDs, weak interoperability, and potential collisions in distributed setups.
  - **Fix:** use UUIDv4 on client and keep strict `thread_id` semantics across frontend/backend.

## 3) Correctness and operability issues

1. **Inconsistent database URL guidance**
  - `backend/env.example` uses `postgresql+asyncpg://...`, while `AsyncPostgresSaver.from_conn_string(...)` typically expects standard Postgres DSN format.
  - Result: misconfiguration risk and startup confusion.
  - **Fix:** normalize docs/env to one validated DSN format and validate at startup.
2. **Excessive `print`-based logging and weak observability**
  - Core path (`api/routes/chat.py`, `api/streaming.py`, `core/nodes/`*) relies heavily on prints.
  - Result: noisy logs, hard filtering, no structured traces.
  - **Fix:** replace with structured logging (JSON or key-value), include `session_id`, node/tool name, event type, latency.
3. **CORS is fully open in app startup**
  - `backend/api/main.py` sets `allow_origins=["*"]`, all methods, all headers.
  - Result: insecure default for non-local use.
  - **Fix:** use environment-based allowed origins and lock down production profile.
4. **Missing quality gates**
  - No visible architecture/integration tests for interrupt/resume, SSE contract, or tool handoff correctness.
  - Result: regressions likely as new subgraphs/tools are added.
  - **Fix:** add async integration tests for:
    - suspend/resume lifecycle
    - `tool_question`/`text_done` SSE ordering
    - collector -> analyzer -> presenter state handoff

## 4) Practical fix sequence (smallest safe path)

1. Add containerization artifacts (infra + backend + frontend).
2. Enforce Postgres checkpointer in non-dev mode.
3. Implement real vector store + retriever and remove `DummyRetriever`.
4. Normalize session/thread IDs to UUID and harden CORS/env profiles.
5. Replace print logging with structured logs and add integration tests.
6. Refactor top-level state contract to reduce Layer 1/Layer 3 coupling.

---

This order gives you fast wins on reliability first (state durability + reproducible infra), then improves retrieval quality, then addresses maintainability and long-term architecture hygiene.