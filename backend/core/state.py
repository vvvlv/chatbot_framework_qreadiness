"""
State schema hierarchy for the three-layer architecture.

Layer 1 (Core): CoreState
Layer 2 (Subgraphs): SubgraphState(CoreState)
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

class CommonToolInput(TypedDict, total=False):
    args: Dict
    nextNode: Optional[str]

class SubgraphState(CoreState, total=False):
    """
#     Layer 2 state - owned by use-case subgraphs.
    
#     Subgraphs may only write to:
#     - Their own fields (workflow-specific)
#     - Layer 2 fields: nextNode, nextData, error...
#     - NOT Layer 1 fields (messages, intent, etc.)
#   """
    currentStep: str # arbitrary name of the current step in which the node is running (eg "collecting", "analysing" or "presenting" in quantum readiness). 
    nextNode: Optional[str] # next node to be executed (in case of conditional edges)
    stepData: Dict # data of the step (eg for "collector" step, stepData is a QuantumDataCollectorState)
    error: Optional[str] # the error message of the last error that occured
    pending_prompt_id: Optional[str] # ?
    common_tool_output: Optional[Dict] # output of common tools (can be any form)
    common_tool_input: Optional[CommonToolInput] # Input data for common tools
