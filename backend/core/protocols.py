"""
Protocols for subgraphs and tools.

Subgraphs and tools must implement these protocols to be registered
in the framework.
"""
from typing import Protocol, Any, Optional


class SubgraphProtocol(Protocol):
    """
    Protocol for Layer 2 use-case subgraphs.
    
    Subgraphs define orchestration logic for their use case:
    which tools run, in what order, and under what conditions.
    They do not implement tool logic itself.
    """
    name: str

    def describe(self) -> str:
        """
        One or two sentences the intent router uses to decide
        whether to dispatch to this subgraph. Be specific.
        
        Example:
        "Assess a company's quantum readiness through a structured
        conversational workflow evaluating cryptographic risk and
        quantum opportunity potential."
        """
        ...

    def build(self) -> Any:
        """
        Return a compiled LangGraph subgraph.
        Called once at application startup.
        """
        ...


class ToolProtocol(Protocol):
    """
    Protocol for Layer 3 tool graphs.
    
    Tools implement reusable interaction patterns.
    They use interrupt() for user input.
    """
    name: str

    def describe(self) -> str:
        """
        Brief description of what the tool does.
        Used for tool selection and documentation.
        """
        ...

    def build(self, args: Optional[dict] = None) -> Any:
        """
        Return a compiled LangGraph tool graph.
        Called once at application startup.
        """
        ...
