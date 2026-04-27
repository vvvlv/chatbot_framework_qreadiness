"""Chat route with SSE streaming and interrupt/resume support."""
import hashlib
import os
import time
from collections import defaultdict, deque
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
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


def _get_interaction_logger(request: Request):
    return getattr(request.app.state, "interaction_logger", None)


async def _log_event_safe(
    logger,
    *,
    session_id: str,
    event_type: str,
    user_message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    if logger is None:
        return
    try:
        await logger.log_event(
            session_id=session_id,
            event_type=event_type,
            user_message=user_message,
            payload=payload or {},
        )
    except Exception as exc:
        # Debug logging must not break chat flow.
        print(f"[CHAT_ROUTE] ⚠ Failed to log interaction event: {exc}")


async def _log_user_message_safe(
    logger,
    *,
    session_id: str,
    message: str,
    is_resume: bool,
    prompt_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if logger is None:
        return
    try:
        await logger.log_user_message(
            session_id=session_id,
            message=message,
            is_resume=is_resume,
            prompt_id=prompt_id,
            metadata=metadata or {},
        )
    except Exception as exc:
        print(f"[CHAT_ROUTE] ⚠ Failed to log user_message row: {exc}")


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
    interaction_logger = _get_interaction_logger(request)
    _enforce_rate_limit(_client_key(request, session_id))
    config = {"configurable": {"thread_id": session_id}}

    # Get graph from app state (set at startup)
    graph = request.app.state.graph

    # Check if graph is suspended (has next checkpoint)
    state = await graph.aget_state(config)
    is_suspended = state and hasattr(state, "next") and state.next

    if is_suspended and len(req.message.encode("utf-8")) > _MAX_RESUME_BYTES:
        await _log_event_safe(
            interaction_logger,
            session_id=session_id,
            event_type="resume_payload_rejected",
            payload={"reason": "too_large"},
        )
        raise HTTPException(status_code=413, detail="Resume payload too large")

    # Handle /cancel command: route through resume path when suspended.
    if req.message.strip().lower() == "/cancel" and is_suspended:
        await _log_user_message_safe(
            interaction_logger,
            session_id=session_id,
            message=req.message,
            is_resume=True,
            prompt_id=req.prompt_id,
            metadata={"kind": "cancel_command"},
        )
        await _log_event_safe(
            interaction_logger,
            session_id=session_id,
            event_type="user_resume_command",
            user_message="/cancel",
            payload={"command": "/cancel"},
        )
        input_ = Command(resume={"text": "/cancel", "prompt_id": req.prompt_id})
        return StreamingResponse(
            stream_graph_events(
                graph,
                input_,
                config,
                interaction_logger=interaction_logger,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Determine input based on suspension state
    if is_suspended:
        pending_prompt_id = None
        if state and hasattr(state, "values") and state.values:
            pending_prompt_id = state.values.get("pending_prompt_id")
        if pending_prompt_id and req.prompt_id != pending_prompt_id:
            await _log_event_safe(
                interaction_logger,
                session_id=session_id,
                event_type="resume_prompt_id_rejected",
                payload={
                    "expected_prompt_id": pending_prompt_id,
                    "provided_prompt_id": req.prompt_id,
                },
            )
            raise HTTPException(
                status_code=409,
                detail="Stale or invalid prompt_id for suspended workflow",
            )
        await _log_event_safe(
            interaction_logger,
            session_id=session_id,
            event_type="user_resume_message",
            user_message=req.message,
            payload={"prompt_id": req.prompt_id},
        )
        await _log_user_message_safe(
            interaction_logger,
            session_id=session_id,
            message=req.message,
            is_resume=True,
            prompt_id=req.prompt_id,
            metadata={"kind": "resume"},
        )
        input_ = Command(resume={"text": req.message, "prompt_id": req.prompt_id})
    else:
        await _log_event_safe(
            interaction_logger,
            session_id=session_id,
            event_type="user_message",
            user_message=req.message,
            payload={"is_new_turn": True},
        )
        await _log_user_message_safe(
            interaction_logger,
            session_id=session_id,
            message=req.message,
            is_resume=False,
            metadata={"kind": "new_turn"},
        )
        input_ = {
            "messages": [HumanMessage(content=req.message)],
            "session_id": session_id,
        }

    # Stream events
    return StreamingResponse(
        stream_graph_events(
            graph,
            input_,
            config,
            interaction_logger=interaction_logger,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/debug/interactions")
async def get_interaction_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    session_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """
    Return recent interaction events captured by the runtime logger.
    This endpoint is intended for lightweight debugging and local observability.
    """
    interaction_logger = _get_interaction_logger(request)
    if interaction_logger is None:
        return {"events": [], "count": 0}
    events = await interaction_logger.recent_events(limit=limit, session_id=session_id)
    return {"events": events, "count": len(events)}