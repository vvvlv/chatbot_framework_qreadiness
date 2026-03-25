"""
Output formatter node - Layer 1 core node.

Normalizes the output from either the subgraph or the fallback LLM
into a final message. Emits the tool_complete or text_done SSE event.
"""
from langchain_core.messages import AIMessage

from core.state import CoreState


async def output_formatter_node(state: CoreState) -> CoreState:
    """
    Format the final output and prepare for streaming.
    
    Takes output from subgraph or fallback_llm and formats it
    as a final message. In a full SSE implementation, this would
    emit tool_complete or text_done events.
    """
    session_id = state.get("session_id", "unknown")
    active_subgraph = state.get("active_subgraph")
    print(f"[OUTPUT_FORMATTER] Formatting output for session: {session_id}, subgraph: {active_subgraph}")
    
    # Get output from state
    output = state.get("output")
    print(f"[OUTPUT_FORMATTER] Output from state: {output[:100] if output else 'None'}...")
    
    if not output:
        # Try to get from subgraph-specific fields
        output = state.get("final_answer") or state.get("current_question") or "No response generated."
    
    # Only add AI message if we have actual output
    if output and output != "No response generated.":
        if "messages" not in state:
            state["messages"] = []
        
        # Only add if last message is not the same (avoid duplicates)
        if not state["messages"] or (
            not hasattr(state["messages"][-1], "content") or 
            state["messages"][-1].content != output
        ):
            state["messages"].append(AIMessage(content=output))
    
    # Mark subgraph as done if it was running
    if state.get("subgraph_status") == "running":
        state["subgraph_status"] = "done"
        print(f"[OUTPUT_FORMATTER] Marked subgraph_status as 'done'")
    
    # Ensure output is set for API response
    state["output"] = output
    print(f"[OUTPUT_FORMATTER] ✓ Final output set ({len(output) if output else 0} chars)")
    
    return state
