"""Chat route with SSE streaming and interrupt/resume support."""
import hashlib
import os
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from api.models import ChatRequest
from api.streaming import stream_graph_events

router = APIRouter(prefix="/api", tags=["chat"])
_REQUEST_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
_REQUESTS_PER_WINDOW = int(os.getenv("RATE_LIMIT_REQUESTS_PER_WINDOW", "45"))
_MAX_RESUME_BYTES = int(os.getenv("MAX_RESUME_BYTES", "8000"))
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request, session_id: str) -> str:
    ip = (request.client.host if request.client else "unknown").strip()
    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    return f"{ip}:{session_hash}"


def _enforce_rate_limit(bucket_key: str) -> None:
    now = time.time()
    queue = _rate_buckets[bucket_key]
    while queue and now - queue[0] > _REQUEST_WINDOW_SECONDS:
        queue.popleft()
    if len(queue) >= _REQUESTS_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    queue.append(now)


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    """Chat endpoint with SSE streaming and interrupt/resume support."""
    session_id = str(req.session_id)
    _enforce_rate_limit(_client_key(request, session_id))
    config = {"configurable": {"thread_id": session_id}}

    # Get graph from app state (set at startup)
    graph = request.app.state.graph

    # Check if graph is suspended (has next checkpoint)
    state = await graph.aget_state(config)
    is_suspended = state and hasattr(state, "next") and state.next

    if is_suspended and len(req.message.encode("utf-8")) > _MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume payload too large")

    # Handle /cancel command: route through resume path when suspended.
    if req.message.strip().lower() == "/cancel" and is_suspended:
        input_ = Command(resume={"text": "/cancel", "prompt_id": req.prompt_id})
        return StreamingResponse(
            stream_graph_events(graph, input_, config),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Determine input based on suspension state
    if is_suspended:
        pending_prompt_id = None
        if state and hasattr(state, "values") and state.values:
            pending_prompt_id = state.values.get("pending_prompt_id")
        if pending_prompt_id and req.prompt_id != pending_prompt_id:
            raise HTTPException(
                status_code=409,
                detail="Stale or invalid prompt_id for suspended workflow",
            )
        input_ = Command(resume={"text": req.message, "prompt_id": req.prompt_id})
    else:
        input_ = {
            "messages": [HumanMessage(content=req.message)],
            "session_id": session_id,
        }

    # Stream events
    return StreamingResponse(
        stream_graph_events(graph, input_, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
