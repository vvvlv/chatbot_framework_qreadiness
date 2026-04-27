"""
Intent router node - Layer 1 core node.

Calls LiteLLM with a classification prompt built from registered
subgraph descriptions. Returns the name of the subgraph to dispatch,
or "fallback" if nothing matches.
"""
from typing import Dict

from core.registry import SubgraphRegistry
from core.state import CoreState
from core.model_gateway import ModelGateway


def create_intent_router_node(registry: SubgraphRegistry, model_gateway: ModelGateway):
    """
    Create intent router node with access to subgraph registry.
    
    The router builds a dynamic routing table from registered subgraphs'
    describe() strings at application startup.
    """
    
    async def intent_router_node(state: CoreState) -> CoreState:
        """
        Classify user intent and route to appropriate subgraph.
        
        Uses LLM to match user input against registered subgraph descriptions.
        Returns subgraph name or "fallback" if no match.
        """
        session_id = state.get("session_id", "unknown")
        print(f"[INTENT_ROUTER] Classifying intent for session: {session_id}")

        sequence = [
            "quantum_competitiveness",
            "cryptographic_risk_security",
            "roadmap_chatbot",
        ]

        def _next_in_sequence(completed: list[str]) -> str | None:
            for chatbot in sequence:
                if chatbot not in completed:
                    return chatbot
            return None

        # If a subgraph is already active/running, keep routing to it.
        # This prevents resumed interrupt answers ("yes", "7 years") from being
        # reclassified as fallback turns.
        active_subgraph = state.get("active_subgraph")
        subgraph_status = state.get("subgraph_status")
        if active_subgraph in registry and subgraph_status == "running":
            print(f"[INTENT_ROUTER] Active subgraph lock detected: {active_subgraph}")
            state["intent"] = active_subgraph
            return state
        
        # Get user message
        messages = state.get("messages", [])
        if not messages:
            print("[INTENT_ROUTER] No messages found, setting intent to None")
            state["intent"] = None
            state["active_subgraph"] = None
            return state
        
        last_message = messages[-1]
        user_input = last_message.content if hasattr(last_message, 'content') else str(last_message)
        print(f"[INTENT_ROUTER] User input: {user_input[:100]}...")
        metadata = state.get("metadata", {}) or {}

        forced_chatbot = metadata.get("selected_chatbot")
        if forced_chatbot in registry:
            print(f"[INTENT_ROUTER] Forced routing to selected_chatbot: {forced_chatbot}")
            state["intent"] = forced_chatbot
            state["active_subgraph"] = forced_chatbot
            state["subgraph_status"] = "running"
            return state

        completed_chatbots = list(metadata.get("completed_chatbots", []))
        if user_input.strip().lower() in {"next", "continue", "continue flow", "next chatbot"}:
            next_chatbot = _next_in_sequence(completed_chatbots)
            if next_chatbot and next_chatbot in registry:
                print(f"[INTENT_ROUTER] Continue intent routed to: {next_chatbot}")
                state["intent"] = next_chatbot
                state["active_subgraph"] = next_chatbot
                state["subgraph_status"] = "running"
                return state
        
        # Build classification prompt from registered subgraphs
        subgraph_descriptions = []
        for name, subgraph in registry.items():
            description = subgraph.describe()
            subgraph_descriptions.append(f"- {name}: {description}")
        
        if not subgraph_descriptions:
            # No subgraphs registered, use fallback
            print("[INTENT_ROUTER] No subgraphs registered, routing to fallback")
            state["intent"] = None
            state["active_subgraph"] = "fallback"
            state["subgraph_status"] = "running"
            return state
        
        print(f"[INTENT_ROUTER] Available subgraphs: {list(registry)}")
        
        classification_prompt = f"""You are an intent classifier for a chatbot system.

The user said: "{user_input}"

Available capabilities:
{chr(10).join(subgraph_descriptions)}

Classify the user's intent. Return ONLY the name of the most appropriate capability, or "fallback" if none match.

Examples:
- User: "I want to assess competitiveness" → quantum_competitiveness
- User: "I want to assess cryptographic risk" → cryptographic_risk_security
- User: "Help me build a roadmap" → roadmap_chatbot
- User: "Hello" → fallback
- User: "Help me with quantum cryptography" → cryptographic_risk_security

Return only the capability name, nothing else."""

        # Call LLM for classification
        try:
            print("[INTENT_ROUTER] Calling LLM for intent classification...")
            response = await model_gateway.chat(
                messages=[{"role": "user", "content": classification_prompt}],
                temperature=0.1,  # Low temperature for classification
            )
            classified_intent = response.strip().lower()
            print(f"[INTENT_ROUTER] LLM classified intent as: '{classified_intent}'")
            
            # Validate that the classified intent exists in registry
            if classified_intent in registry:
                print(f"[INTENT_ROUTER] ✓ Routing to subgraph: {classified_intent}")
                state["intent"] = classified_intent
                state["active_subgraph"] = classified_intent
                state["subgraph_status"] = "running"
            else:
                # Fallback if classification doesn't match any subgraph
                print(f"[INTENT_ROUTER] ⚠ Classified intent '{classified_intent}' not in registry, using fallback")
                state["intent"] = None
                state["active_subgraph"] = "fallback"
                state["subgraph_status"] = "running"
        except Exception as e:
            print(f"[INTENT_ROUTER] ✗ Error during classification: {e}")
            import traceback
            traceback.print_exc()
            # Fallback on error
            state["intent"] = None
            state["active_subgraph"] = "fallback"
            state["subgraph_status"] = "running"
        
        print(f"[INTENT_ROUTER] Final routing decision: active_subgraph={state.get('active_subgraph')}, intent={state.get('intent')}")
        return state
    
    return intent_router_node
