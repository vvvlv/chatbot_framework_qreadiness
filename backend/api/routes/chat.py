"""
Chat route with SSE streaming and interrupt/resume support.

According to app_definition.md Section 6, the API must:
- Detect suspended checkpoints and use Command(resume=...) to continue
- Stream events via graph.astream_events()
- Handle /cancel command for escaping tools
"""
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from api.models import ChatRequest
from api.streaming import stream_graph_events

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    """
    Chat endpoint with SSE streaming and interrupt/resume support.
    
    According to app_definition.md:
    - Checks for suspended checkpoint (state.next)
    - Uses Command(resume=...) if suspended, otherwise normal invocation
    - Streams typed SSE events
    - Handles /cancel command for escaping tools
    """
    print(f"\n[API_CHAT] ========================================")
    print(f"[API_CHAT] New request - session_id: {req.session_id}")
    print(f"[API_CHAT] Message: {req.message[:100]}...")
    
    config = {"configurable": {"thread_id": req.session_id}}
    
    # Get graph from app state (set at startup)
    graph = request.app.state.graph
    
    # Check if graph is suspended (has next checkpoint)
    state = await graph.aget_state(config)
    is_suspended = state and hasattr(state, "next") and state.next
    print(f"[API_CHAT] Graph suspended: {is_suspended}")
    
    # Handle /cancel command
    if req.message.strip().lower().startswith("/cancel"):
        print("[API_CHAT] /cancel command received")
        if state and hasattr(state, "next") and state.next:
            print("[API_CHAT] Clearing suspended state...")
            # Clear suspended state
            await graph.aupdate_state(
                config,
                {
                    "active_tool": None,
                    "tool_status": "idle",
                    "active_subgraph": None,
                    "subgraph_status": "idle",
                    "output": "Tool cancelled.",
                },
                as_node="output_formatter",
            )
            # Stream cancellation acknowledgement
            async def cancel_response():
                yield f"data: {json.dumps({'type': 'text_done', 'payload': {'full_text': 'Tool cancelled.'}, 'meta': {'session_id': req.session_id}})}\n\n"
            return StreamingResponse(
                cancel_response(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            print("[API_CHAT] No active tool to cancel")
    
    # Determine input based on suspension state
    if is_suspended:
        # Graph is suspended — this message resumes a tool
        print(f"[API_CHAT] Resuming suspended graph with message: {req.message[:50]}...")
        input_ = Command(resume=req.message)
    else:
        # Fresh turn — normal invocation
        print(f"[API_CHAT] Fresh turn - normal invocation")
        input_ = {
            "messages": [HumanMessage(content=req.message)],
            "session_id": req.session_id,
        }
    
    print(f"[API_CHAT] Starting SSE stream...")
    # Stream events
    return StreamingResponse(
        stream_graph_events(graph, input_, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
