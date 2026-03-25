"""
Core Layer (Layer 1) - Platform-owned, never modified by applications.

According to app_definition.md Section 3.1, this layer contains:
- session_manager: Trims messages, injects system prompt
- intent_router: Classifies intent and routes to subgraph
- fallback_llm: Plain conversational LLM when no subgraph matches
- output_formatter: Normalizes output and emits events
"""
from core.graph import build_core_graph
from core.checkpointer import get_checkpointer
from core.llm import get_model_gateway, llm
from core.vector_store import get_vector_store
from core.protocols import SubgraphProtocol, ToolProtocol
from core.registry import SubgraphRegistry
from core.state import CoreState, SubgraphState, ToolState

__all__ = [
    "build_core_graph",
    "get_checkpointer",
    "get_model_gateway",
    "llm",
    "get_vector_store",
    "SubgraphProtocol",
    "ToolProtocol",
    "SubgraphRegistry",
    "CoreState",
    "SubgraphState",
    "ToolState",
]
