"""
SSE event streaming implementation.

According to app_definition.md Section 7, all events follow a typed envelope:
{
  "type": "<event_type>",
  "payload": {},
  "meta": {
    "session_id": "<str>",
    "current_step": "<step_name> | null",
    "resumable": "<bool>",
    "can_escape": "<bool>",
    "pending_prompt_id": "<str>"
  }
}
"""
import json
import traceback
from typing import Any, AsyncIterator, Dict, Optional

from langgraph.types import Command
from api.custom_events import eventSelector


def _extract_interrupt_payload(state) -> Optional[Dict]:
    if not state or not hasattr(state, "tasks") or not state.tasks:
        return None
    for task in state.tasks:
        interrupts = getattr(task, "interrupts", None)
        if not interrupts:
            continue
        for intr in interrupts:
            value = getattr(intr, "value", None)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                return {"text": value, "input_type": "free_text"}
    return None


async def stream_graph_events(
    graph,
    input_,
    config: Dict,
    user_id: str,
    interaction_logger=None,
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

    async def _log_event(
        event_type: str,
        *,
        app_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if interaction_logger is None:
            return
        try:
            await interaction_logger.log_event(
                session_id=session_id,
                event_type=event_type,
                user_id=user_id,
                app_name=app_name,
                tool_name=tool_name,
                payload=payload or {},
            )
        except Exception as exc:
            print(f"[SSE_STREAM] ⚠ Failed to persist interaction event: {exc}")
    
    current_meta = _build_meta(config, None)
    await _log_event("stream_start", payload={"is_resume": is_resume})

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
                meta = await _refresh_meta()
                type_, payload, meta = await eventSelector(name, data, meta, _log_event)
                yield _sse(type_, payload, meta)
            
            elif kind == "on_chain_error":
                # Error handling
                error_data = event.get("data", {})
                error_msg = str(error_data.get("error", "Unknown error"))
                print(f"[SSE_STREAM] ✗ Chain error: {error_msg}")
                await _log_event(
                    "chain_error",
                    payload={"message": error_msg},
                )
                yield _sse("error", {
                    "message": error_msg,
                    "recoverable": False,
                }, await _refresh_meta())
            
            elif kind == "on_chain_start":
                # begining of a node/subgraph
                node_name = event.get("name", "")
                if node_name:
                    print(f"[SSE_STREAM] Node started: {node_name}")
                    await _log_event(
                        "app_node_start",
                        app_name=node_name,
                        payload={"node": node_name},
                    )
            
            elif kind == "on_chain_end":
                # end of a node/subgraph
                node_name = event.get("name", "")
                if node_name:
                    print(f"[SSE_STREAM] Node ended: {node_name}")
                    await _log_event(
                        "app_node_end",
                        app_name=node_name,
                        payload={"node": node_name},
                    )
    
    except Exception as e:
        # Catch any streaming errors
        print(f"[SSE_STREAM] ✗ Streaming error: {e}")
        await _log_event("stream_error", payload={"message": str(e)})
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
            print(f"[SSE_STREAM] Interrupt - Waiting for user input")
            interrupt_values = _extract_interrupt_payload(final_state)
            meta = await _refresh_meta()
            if meta.get("pending_prompt_id", None) == None:
                meta["pending_prompt_id"] = interrupt_values.get("prompt_id", None)
            if interrupt_values.get("prompt_id", None) == None:
                interrupt_values["prompt_id"] = meta.get("pending_prompt_id", None)
            await _log_event(
                interrupt_values.get("event_name", "interrupt"),
                payload=interrupt_values,
            )
            yield _sse(
                interrupt_values.get("event_name", "interrupt"),
                interrupt_values,
                meta,
            )

        else:
            final_output: Optional[str] = None
            if final_state and hasattr(final_state, "values") and final_state.values:
                values = final_state.values
                candidate = values.get("output")
                if isinstance(candidate, str) and candidate.strip():
                    final_output = candidate

            if final_output:
                print(f"[SSE_STREAM] Emitting text_done ({len(final_output)} chars)")
                step_data = {}
                if final_state and hasattr(final_state, "values") and final_state.values:
                    step_data = final_state.values.get("stepData", {}) or {}
                report_save_opt_out = bool(step_data.get("report_save_opt_out", False))
                is_quantum_report = "QUANTUM READINESS REPORT" in final_output
                if is_quantum_report and interaction_logger is not None:
                    if report_save_opt_out:
                        await _log_event(
                            "final_report_not_saved",
                            payload={"reason": "opt_out"},
                        )
                    else:
                        try:
                            await interaction_logger.log_final_report(
                                session_id=session_id,
                                user_id=user_id,
                                report_text=final_output,
                                company_name=step_data.get("company_name") or step_data.get("company_name_for_report"),
                                industry=step_data.get("industry"),
                                metadata={
                                    "archetype": step_data.get("archetype"),
                                    "quantum_opportunity_score": step_data.get("quantum_opportunity_score"),
                                },
                            )
                            await _log_event(
                                "final_report_saved",
                                payload={"saved": True},
                            )
                        except Exception as exc:
                            print(f"[SSE_STREAM] ⚠ Failed to persist final report: {exc}")
                            await _log_event(
                                "final_report_save_failed",
                                payload={"error": str(exc)},
                            )
                await _log_event(
                    "stream_output_complete",
                    payload={"output_length": len(final_output)},
                )
                yield _sse("text_done", {"full_text": final_output}, await _refresh_meta())
            else:
                print("[SSE_STREAM] No final output found to emit as text_done")
    except Exception as e:
        print(f"[SSE_STREAM] ⚠ Could not emit final SSE event from state: {e}")

    print(f"[SSE_STREAM] Stream complete - processed {event_count} events")
    await _log_event("stream_complete", payload={"event_count": event_count})


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


def _build_meta(config: Dict, state) -> Dict: # TODO: update with new states
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
        "current_step": None,
        "resumable": False,
        "can_escape": False,
        "pending_prompt_id": None,
    }
    
    if state:
        # Check if graph is suspended (has next checkpoint)
        if hasattr(state, "next") and state.next:
            meta["resumable"] = True
            meta["can_escape"] = True
        
        # Extract metadata from state if available
        if hasattr(state, "values") and state.values:
            values = state.values
            meta["current_step"] = values.get("currentStep")
            meta["pending_prompt_id"] = values.get("pending_prompt_id")
        
        # TODO : other metadata from state snapshot ?
    
    return meta
