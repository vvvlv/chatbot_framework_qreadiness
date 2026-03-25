"""
SSE event streaming implementation.

According to app_definition.md Section 7, all events follow a typed envelope:
{
  "type": "<event_type>",
  "payload": {},
  "meta": {
    "session_id": "<str>",
    "active_tool": "<tool_name> | null",
    "tool_step": "<int> | null",
    "tool_total": "<int> | null",
    "resumable": "<bool>",
    "can_escape": "<bool>"
  }
}
"""
import json
from typing import AsyncIterator, Dict, Optional

from langgraph.types import Command


def _extract_interrupt_question(state) -> Optional[str]:
    """
    Best-effort extraction of interrupt question text from suspended state.
    """
    if not state or not hasattr(state, "tasks") or not state.tasks:
        return None

    for task in state.tasks:
        interrupts = getattr(task, "interrupts", None)
        if not interrupts:
            continue
        for intr in interrupts:
            value = getattr(intr, "value", None)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                text = value.get("text") or value.get("question")
                if isinstance(text, str) and text.strip():
                    return text
    return None


async def stream_graph_events(
    graph,
    input_,
    config: Dict,
) -> AsyncIterator[str]:
    """
    Stream graph execution events as SSE.
    
    Handles:
    - LLM token streaming (text_delta events)
    - Custom events (tool_start, tool_question, tool_progress, tool_complete)
    - Errors (error events)
    - Session state (session_state events)
    
    Args:
        graph: Compiled LangGraph
        input_: Graph input (dict or Command)
        config: Graph config with thread_id
    
    Yields:
        SSE-formatted event strings
    """
    session_id = config.get("configurable", {}).get("thread_id", "unknown")
    is_resume = isinstance(input_, Command)
    print(f"[SSE_STREAM] Starting stream for session: {session_id}, resume: {is_resume}")
    
    current_meta = _build_meta(config, None)

    async def _refresh_meta() -> Dict:
        nonlocal current_meta
        try:
            state = await graph.aget_state(config)
            current_meta = _build_meta(config, state)
        except Exception as e:
            print(f"[SSE_STREAM] ⚠ Error refreshing state meta: {e}")
            current_meta = _build_meta(config, None)
        return current_meta
    
    # Emit session_state event first
    yield _sse("session_state", {}, await _refresh_meta())
    print(f"[SSE_STREAM] Emitted session_state event")
    
    # Stream graph execution events
    event_count = 0
    emitted_tool_question = False
    last_tool_question_text = None
    try:
        async for event in graph.astream_events(input_, config=config, version="v2"):
            event_count += 1
            kind = event.get("event")
            name = event.get("name", "")
            
            if event_count % 10 == 0:  # Log every 10th event to avoid spam
                print(f"[SSE_STREAM] Processed {event_count} events, current: {kind}/{name}")
            
            if kind == "on_chat_model_stream":
                # LLM token streaming
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    token = chunk.content
                    if token:
                        yield _sse("text_delta", {"token": token}, await _refresh_meta())
            
            elif kind == "on_custom_event":
                # Custom events from tools/subgraphs
                name = event.get("name")
                data = event.get("data", {})
                
                if name == "tool_start":
                    print(f"[SSE_STREAM] Tool started: {data.get('tool_name')}")
                    meta = await _refresh_meta()
                    yield _sse("tool_start", data, {
                        **meta,
                        "active_tool": data.get("tool_name"),
                        "tool_total": data.get("total_steps"),
                    })
                
                elif name == "tool_question":
                    print(f"[SSE_STREAM] Tool question: {data.get('text', '')[:50]}...")
                    text = data.get("text")
                    # Deduplicate identical tool_question emissions within the same stream.
                    if isinstance(text, str) and text.strip():
                        if text == last_tool_question_text:
                            continue
                        last_tool_question_text = text

                    emitted_tool_question = True
                    meta = await _refresh_meta()
                    yield _sse(
                        "tool_question",
                        data,
                        {
                        **meta,
                        "resumable": True,
                        "can_escape": True,
                        "tool_step": data.get("step"),
                        },
                    )
                
                elif name in ("tool_progress", "tool_complete"):
                    print(f"[SSE_STREAM] Tool {name}: {data}")
                    yield _sse(name, data, await _refresh_meta())
            
            elif kind == "on_chain_error":
                # Error handling
                error_data = event.get("data", {})
                error_msg = str(error_data.get("error", "Unknown error"))
                print(f"[SSE_STREAM] ✗ Chain error: {error_msg}")
                yield _sse("error", {
                    "message": error_msg,
                    "recoverable": False,
                }, await _refresh_meta())
            
            elif kind == "on_chain_start":
                node_name = event.get("name", "")
                if node_name:
                    print(f"[SSE_STREAM] Node started: {node_name}")
            
            elif kind == "on_chain_end":
                node_name = event.get("name", "")
                if node_name:
                    print(f"[SSE_STREAM] Node ended: {node_name}")
    
    except Exception as e:
        # Catch any streaming errors
        print(f"[SSE_STREAM] ✗ Streaming error: {e}")
        import traceback
        traceback.print_exc()
        yield _sse("error", {
            "message": str(e),
            "recoverable": False,
        }, await _refresh_meta())
    
    # Emit final event based on whether run completed or suspended on interrupt().
    try:
        final_state = await graph.aget_state(config)
        is_suspended_now = bool(
            final_state and hasattr(final_state, "next") and final_state.next
        )

        if is_suspended_now:
            question = _extract_interrupt_question(final_state)
            # The tool typically already emits tool_question before calling interrupt().
            # Avoid duplicating the same question here.
            if question and not emitted_tool_question:
                print(f"[SSE_STREAM] Emitting tool_question ({len(question)} chars)")
                yield _sse(
                    "tool_question",
                    {"text": question, "input_type": "free_text"},
                    {**await _refresh_meta(), "resumable": True, "can_escape": True},
                )
            else:
                print("[SSE_STREAM] Suspended run without extractable interrupt question")
        else:
            final_output: Optional[str] = None
            if final_state and hasattr(final_state, "values") and final_state.values:
                values = final_state.values
                candidate = values.get("output")
                if isinstance(candidate, str) and candidate.strip():
                    final_output = candidate

            if final_output:
                print(f"[SSE_STREAM] Emitting text_done ({len(final_output)} chars)")
                yield _sse("text_done", {"full_text": final_output}, await _refresh_meta())
            else:
                print("[SSE_STREAM] No final output found to emit as text_done")
    except Exception as e:
        print(f"[SSE_STREAM] ⚠ Could not emit final SSE event from state: {e}")

    print(f"[SSE_STREAM] Stream complete - processed {event_count} events")


def _sse(type_: str, payload: Dict, meta: Dict) -> str:
    """
    Format an SSE event with typed envelope.
    
    Args:
        type_: Event type (session_state, text_delta, tool_start, etc.)
        payload: Event-specific data
        meta: Metadata (session_id, active_tool, resumable, etc.)
    
    Returns:
        SSE-formatted string: "data: {json}\n\n"
    """
    event = {
        "type": type_,
        "payload": payload,
        "meta": meta,
    }
    return f"data: {json.dumps(event)}\n\n"


def _build_meta(config: Dict, state) -> Dict:
    """
    Build metadata for SSE events.
    
    Args:
        config: Graph config with thread_id
        state: Current graph state (or None)
    
    Returns:
        Metadata dict with session_id, active_tool, resumable, etc.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    
    meta = {
        "session_id": thread_id,
        "active_tool": None,
        "tool_step": None,
        "tool_total": None,
        "resumable": False,
        "can_escape": False,
    }
    
    if state:
        # Check if graph is suspended (has next checkpoint)
        if hasattr(state, "next") and state.next:
            meta["resumable"] = True
            meta["can_escape"] = True
        
        # Extract active_tool from state if available
        if hasattr(state, "values") and state.values:
            values = state.values
            meta["active_tool"] = values.get("active_tool")
            if meta["active_tool"]:
                # Try to extract tool step info from state
                tool_output = values.get("tool_output", {})
                if isinstance(tool_output, dict):
                    meta["tool_step"] = tool_output.get("step")
                    meta["tool_total"] = tool_output.get("total")
    
    return meta
