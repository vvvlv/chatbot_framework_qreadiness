"""Chat route with SSE streaming and interrupt/resume support."""
import hashlib
import uuid
import os
import time
import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from api.models import ChatRequest, HistoryRequest
from api.report_metadata import build_report_download_metadata, extract_step_data_from_state
from api.streaming import stream_graph_events
from core.usage_context import clear_usage_context, set_usage_context

router = APIRouter(prefix="/api", tags=["chat"])
_REQUEST_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
_REQUESTS_PER_WINDOW = int(os.getenv("RATE_LIMIT_REQUESTS_PER_WINDOW", "45"))
_MAX_RESUME_BYTES = int(os.getenv("MAX_RESUME_BYTES", "8000"))
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def _get_interaction_logger(request: Request):
    return getattr(request.app.state, "interaction_logger", None)


def _get_usage_tracker(request: Request):
    return getattr(request.app.state, "usage_tracker", None)


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


async def _log_event_safe(
    logger,
    *,
    session_id: str,
    event_type: str,
    user_id: str,
    user_message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    if logger is None:
        return
    try:
        await logger.log_event(
            session_id=session_id,
            event_type=event_type,
            user_id=user_id,
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
    user_id: str,
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
            user_id=user_id,
            message=message,
            is_resume=is_resume,
            prompt_id=prompt_id,
            metadata=metadata or {},
        )
    except Exception as exc:
        print(f"[CHAT_ROUTE] ⚠ Failed to log user_message row: {exc}")


def _client_key(request: Request, user_id: str) -> str:
    ip = (request.client.host if request.client else "unknown").strip()
    session_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
    return f"{ip}:{session_hash}"


def _enforce_rate_limit(bucket_key: str) -> None:
    now = time.time()
    queue = _rate_buckets[bucket_key]
    while queue and now - queue[0] > _REQUEST_WINDOW_SECONDS:
        queue.popleft()
    if len(queue) >= _REQUESTS_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    queue.append(now)

def _node_name_to_class_name(node_name: str) -> str:
    if node_name == "data_collector":
        return "quantum_data_collector"
    elif node_name == "analyzer":
        return "quantum_analyzer"
    elif node_name == "presenter":
        return "quantum_presenter"
    else:
        return None


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    """Chat endpoint with SSE streaming and interrupt/resume support."""
    session_id = str(req.session_id)
    user_id = str(req.user_id)
    interaction_logger = _get_interaction_logger(request)
    set_usage_context(session_id=session_id, user_id=user_id)
    _enforce_rate_limit(_client_key(request, user_id))
    config = {"configurable": {"thread_id": session_id}}
    queue = asyncio.Queue()
    request.app.state.active_queues[session_id] = queue

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
            user_id=user_id,
            payload={"reason": "too_large"},
        )
        raise HTTPException(status_code=413, detail="Resume payload too large")

    # Handle /cancel command: route through resume path when suspended.
    if req.message.strip().lower() == "/cancel" and is_suspended:
        await _log_user_message_safe(
            interaction_logger,
            session_id=session_id,
            user_id=user_id,
            message=req.message,
            is_resume=True,
            prompt_id=req.prompt_id,
            metadata={"kind": "cancel_command"},
        )
        await _log_event_safe(
            interaction_logger,
            session_id=session_id,
            event_type="user_resume_command",
            user_id=user_id,
            user_message="/cancel",
            payload={"command": "/cancel"},
        )
        input_ = Command(resume={"text": "/cancel", "prompt_id": req.prompt_id})

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
                user_id=user_id,
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
            user_id=user_id,
            user_message=req.message,
            payload={"prompt_id": req.prompt_id},
        )
        await _log_user_message_safe(
            interaction_logger,
            session_id=session_id,
            user_id=user_id,
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
            user_id=user_id,
            user_message=req.message,
            payload={"is_new_turn": True},
        )
        await _log_user_message_safe(
            interaction_logger,
            session_id=session_id,
            user_id=user_id,
            message=req.message,
            is_resume=False,
            metadata={"kind": "new_turn"},
        )
        input_ = {
            "messages": [HumanMessage(content=req.message)],
            "session_id": session_id,
        }

    asyncio.create_task(
        stream_graph_events(
            graph,
            input_,
            config,
            user_id,
            queue,
            interaction_logger=interaction_logger,
        )
    )

    async def generator():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            clear_usage_context()
    
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/getHistory")
async def get_history(req: HistoryRequest, request: Request) -> list[Dict]:
    session_id = str(req.session_id)
    config = {"configurable": {"thread_id": session_id}}
    queue = request.app.state.active_queues.get(session_id)
    graph = request.app.state.graph
    full_state = await graph.aget_state(config, subgraphs=True)
    state = full_state
    current_subgraph = None
    is_graph_running = True
    if state and hasattr(state, "tasks") and len(state.tasks) > 0:
        state = state.tasks[0].state
    if state and hasattr(state, "tasks") and len(state.tasks) > 0:
        current_subgraph = state.tasks[0].name
        state = state.tasks[0].state
    if state and hasattr(state, "tasks") and len(state.tasks) > 0 and state.tasks[0].name == "interrupt":
        is_graph_running = False
        state = state.tasks[0].state
    values = {}
    if state and hasattr(state, "values"):
        values = state.values
    messages = values.get("messages") or []
    stepData = extract_step_data_from_state(full_state)
    step = stepData.get("step") or 0
    field_status = stepData.get("field_status") or {}
    prompt_id = values.get("pending_prompt_id") or None
    total = len(field_status.keys())
    print("[GET HISTORY] messages :", messages)
    print("[GET_HISTORY] current_node :", current_subgraph)

    # Convert BaseMessages to message type of frontend
    formatted_messages = map(lambda msg: {
        "id": str(uuid.uuid4()),
        "role": "user" if hasattr(msg, "type") and msg.type == "human" else "assistant",
        "content": msg.content if hasattr(msg, "content") else str(msg),
        "date": time.time()
    }, messages)
    message_event = {
        "type": "get_history",
        "payload": {
            "messages": list(formatted_messages),
        },
        "meta": {},
    }
    tool_meta_event = {
        "type": "get_tool_meta",
        "payload": {
            "name": _node_name_to_class_name(current_subgraph),
            "step": step,
            "total": total,
            "is_graph_running": is_graph_running,
            "prompt_id": prompt_id,
        },
        "meta": {},
    }
    report_metadata = None
    output_text = str(values.get("output") or "")
    if "QUANTUM READINESS REPORT" in output_text:
        report_metadata = build_report_download_metadata(stepData)
        if report_metadata:
            report_metadata["report_text"] = output_text

    async def generator(messages, toolMeta, reportMeta):
        try:
            yield f"data: {json.dumps(messages)}\n\n"
            yield f"data: {json.dumps(toolMeta)}\n\n"
            if reportMeta:
                report_meta_event = {
                    "type": "report_metadata",
                    "payload": reportMeta,
                    "meta": {},
                }
                yield f"data: {json.dumps(report_meta_event)}\n\n"
            while True and queue is not None:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            clear_usage_context()
    
    return StreamingResponse(
        generator(message_event, tool_meta_event, report_metadata),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/debug/usage")
async def get_usage_stats(
    request: Request,
    session_id: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    start: Optional[str] = Query(default=None, description="ISO-8601 start datetime"),
    end: Optional[str] = Query(default=None, description="ISO-8601 end datetime"),
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    """
    Return LLM usage aggregates for a timeframe (global, per session, per model, per day).
    """
    usage_tracker = _get_usage_tracker(request)
    if usage_tracker is None:
        return {"error": "Usage tracker not configured", "totals": {}}
    try:
        return await usage_tracker.get_stats(
            session_id=session_id,
            user_id=user_id,
            start=_parse_iso_datetime(start),
            end=_parse_iso_datetime(end),
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid datetime filter: {exc}") from exc


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