"""
State schema hierarchy for the three-layer architecture.

Layer 1 (Core): CoreState
Layer 2 (Subgraphs): SubgraphState(CoreState)
Layer 3 (Tools): ToolState(SubgraphState)
"""
from typing import Annotated, Dict, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CoreState(TypedDict, total=False):
    """
    Layer 1 state - owned by core graph.
    
    Core nodes may only write to these fields:
    - messages, output, intent, active_subgraph, subgraph_status, metadata
    """
    # Communication
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    output: Optional[str]

    # Routing
    intent: Optional[str]  # set by intent_router
    active_subgraph: Optional[str]  # name of currently running subgraph
    subgraph_status: Literal["idle", "running", "done", "error"]

    # Passthrough
    metadata: Dict  # session-level context (user_id, locale, etc.)


class SubgraphState(CoreState, total=False):
    """
    Layer 2 state - owned by use-case subgraphs.
    
    Subgraphs may only write to:
    - Their own fields (workflow-specific)
    - Layer 2 fields: active_tool, tool_status, tool_input, tool_output
    - NOT Layer 1 fields (messages, intent, etc.)
    """
    active_tool: Optional[str]
    tool_status: Literal["idle", "running", "done", "error"]
    tool_input: Dict  # data passed INTO the tool
    tool_output: Dict  # data returned FROM the tool


class ToolState(SubgraphState, total=False):
    """
    Layer 3 state - owned by tool graphs.
    
    Tools may only write to:
    - Their own tool-specific fields
    - Layer 3 fields: step, step_data, is_complete, error
    - NOT Layer 1 or Layer 2 fields
    """
    step: int
    step_data: Dict  # accumulated data across steps
    is_complete: bool
    error: Optional[str]
