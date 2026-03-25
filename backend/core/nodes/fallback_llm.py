"""
Fallback LLM node - Layer 1 core node.

Plain conversational LLM call via LiteLLM.
Used when no subgraph matches the intent, or when a tool error ejects to the core.
"""
from langchain_core.messages import HumanMessage

from core.state import CoreState
from core.model_gateway import ModelGateway


async def fallback_llm_node(state: CoreState, model_gateway: ModelGateway) -> CoreState:
    """
    Generate a conversational response when no subgraph matches.
    
    This is the default behavior for general conversation.
    """
    session_id = state.get("session_id", "unknown")
    print(f"[FALLBACK_LLM] Generating response for session: {session_id}")
    
    messages = state.get("messages", [])
    if not messages:
        print("[FALLBACK_LLM] No messages, returning greeting")
        state["output"] = "Hello! How can I help you today?"
        return state
    
    # Get last user message
    last_message = messages[-1]
    user_input = last_message.content if hasattr(last_message, 'content') else str(last_message)
    print(f"[FALLBACK_LLM] User message: {user_input[:100]}...")
    
    # Build conversation context
    conversation_context = []
    for msg in messages[-5:]:  # Last 5 messages for context
        role = "user" if hasattr(msg, 'type') and msg.type == "human" else "assistant"
        content = msg.content if hasattr(msg, 'content') else str(msg)
        conversation_context.append({"role": role, "content": content})
    
    # Add system prompt
    system_prompt = {
        "role": "system",
        "content": "You are a helpful AI assistant. Provide clear, concise, and helpful responses."
    }
    
    llm_messages = [system_prompt] + conversation_context
    
    try:
        print(f"[FALLBACK_LLM] Calling LLM with {len(llm_messages)} messages...")
        response = await model_gateway.chat(
            messages=llm_messages,
            temperature=0.7,
        )
        print(f"[FALLBACK_LLM] ✓ LLM response received ({len(response)} chars)")
        state["output"] = response
    except Exception as e:
        print(f"[FALLBACK_LLM] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        state["output"] = "I apologize, but I'm having trouble processing your request right now. Please try again."
    
    return state
