"""
Core graph builder - Layer 1.

Builds the core graph with session_manager, intent_router, fallback_llm,
and output_formatter nodes. Registers all subgraphs dynamically.
"""
from langgraph.graph import END, START, StateGraph

from core.nodes.fallback_llm import fallback_llm_node
from core.nodes.intent_router import create_intent_router_node
from core.nodes.output_formatter import output_formatter_node
from core.nodes.session_manager import session_manager_node
from core.registry import SubgraphRegistry
from core.state import CoreState
from core.model_gateway import ModelGateway


def build_core_graph(
    registry: SubgraphRegistry,
    model_gateway: ModelGateway,
    checkpointer=None,
):
    """
    Build the core graph (Layer 1).
    
    The core graph contains four fixed nodes:
    - session_manager: Trims messages, injects system prompt
    - intent_router: Classifies intent and routes to subgraph
    - fallback_llm: Plain conversational LLM when no subgraph matches
    - output_formatter: Normalizes output and emits events
    
    All registered subgraphs are added as nodes dynamically.
    
    Args:
        registry: SubgraphRegistry with registered subgraphs
        model_gateway: ModelGateway for LLM calls
        checkpointer: Optional checkpointer (defaults to InMemorySaver)
    
    Returns:
        Compiled graph ready for execution
    """
    graph = StateGraph(CoreState)
    
    # Create async wrapper for fallback_llm_node
    async def fallback_llm_wrapper(state: CoreState) -> CoreState:
        return await fallback_llm_node(state, model_gateway)
    
    # Add core nodes
    graph.add_node("session_manager", session_manager_node)
    graph.add_node("intent_router", create_intent_router_node(registry, model_gateway))
    graph.add_node("fallback_llm", fallback_llm_wrapper)
    graph.add_node("output_formatter", output_formatter_node)
    
    # Register each subgraph as a node by name
    for name, subgraph in registry.items():
        compiled_subgraph = subgraph.build()
        graph.add_node(name, compiled_subgraph)
        # All subgraphs route to output_formatter when done
        graph.add_edge(name, "output_formatter")
    
    # Set entry point
    graph.set_entry_point("session_manager")
    
    # Linear flow: session_manager -> intent_router
    graph.add_edge("session_manager", "intent_router")
    
    # Intent router routes to subgraph or fallback
    def route_to_subgraph_or_fallback(state: CoreState) -> str:
        """Route based on intent_router's decision."""
        active_subgraph = state.get("active_subgraph")
        intent = state.get("intent")
        
        print(f"[CORE_GRAPH] Routing decision - active_subgraph: {active_subgraph}, intent: {intent}")
        
        if active_subgraph and active_subgraph in registry:
            print(f"[CORE_GRAPH] → Routing to subgraph: {active_subgraph}")
            return active_subgraph
        else:
            print(f"[CORE_GRAPH] → Routing to fallback_llm")
            return "fallback_llm"
    
    # Build routing map dynamically
    routing_map = {"fallback_llm": "fallback_llm"}
    for name in registry:
        routing_map[name] = name
    
    graph.add_conditional_edges(
        "intent_router",
        route_to_subgraph_or_fallback,
        routing_map,
    )
    
    # Fallback LLM routes to output_formatter
    graph.add_edge("fallback_llm", "output_formatter")
    
    # Output formatter is the end
    graph.add_edge("output_formatter", END)
    
    # Use provided checkpointer or default to InMemorySaver
    from langgraph.checkpoint.memory import InMemorySaver
    if checkpointer is None:
        checkpointer = InMemorySaver()
    
    return graph.compile(checkpointer=checkpointer)
