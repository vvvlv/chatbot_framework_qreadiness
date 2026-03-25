"""
Session manager node - Layer 1 core node.

Trims message history to fit context window.
Injects system prompt.
Sets session-level metadata.
"""
from typing import Dict

from core.state import CoreState


async def session_manager_node(state: CoreState) -> CoreState:
    """
    Manage session state and prepare messages for processing.
    
    - Trims message history to fit context window
    - Injects system prompt if needed
    - Sets session-level metadata (user_id, locale, active_tool)
    """
    session_id = state.get("session_id", "unknown")
    print(f"[SESSION_MANAGER] Processing session: {session_id}")
    
    messages = state.get("messages", [])
    print(f"[SESSION_MANAGER] Current message count: {len(messages)}")
    
    # Trim messages if needed (keep last N messages)
    max_messages = 20  # Configurable
    if len(messages) > max_messages:
        trimmed = len(messages) - max_messages
        state["messages"] = messages[-max_messages:]
        print(f"[SESSION_MANAGER] Trimmed {trimmed} messages (kept last {max_messages})")
    
    # Ensure metadata exists
    if "metadata" not in state:
        state["metadata"] = {}
    
    # Set session metadata
    state["metadata"]["session_id"] = session_id
    if "user_id" in state:
        state["metadata"]["user_id"] = state["user_id"]
    
    # Initialize subgraph status if not set
    if "subgraph_status" not in state:
        state["subgraph_status"] = "idle"
    
    print(f"[SESSION_MANAGER] Session status: {state.get('subgraph_status')}, active_subgraph: {state.get('active_subgraph')}")
    return state
