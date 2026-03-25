"""
Subgraph registry for automatic intent routing.

The registry collects all subgraphs at startup. The intent_router
uses their describe() strings to build a dynamic routing table.
"""
from typing import Dict

from core.protocols import SubgraphProtocol


class SubgraphRegistry:
    """
    Registry for Layer 2 subgraphs.
    
    Subgraphs are registered at startup. The intent_router
    automatically routes requests based on their describe() strings.
    """
    
    def __init__(self):
        self._subgraphs: Dict[str, SubgraphProtocol] = {}
    
    def register(self, subgraph: SubgraphProtocol) -> None:
        """
        Register a subgraph.
        
        Args:
            subgraph: Subgraph implementing SubgraphProtocol
        """
        if not hasattr(subgraph, 'name') or not subgraph.name:
            raise ValueError(f"Subgraph must have a 'name' attribute: {subgraph}")
        
        if not hasattr(subgraph, 'describe') or not callable(subgraph.describe):
            raise ValueError(f"Subgraph must implement 'describe()' method: {subgraph}")
        
        if not hasattr(subgraph, 'build') or not callable(subgraph.build):
            raise ValueError(f"Subgraph must implement 'build()' method: {subgraph}")
        
        self._subgraphs[subgraph.name] = subgraph
        print(f"✓ Registered subgraph: {subgraph.name} - {subgraph.describe()}")
    
    def get(self, name: str) -> SubgraphProtocol:
        """Get a subgraph by name."""
        return self._subgraphs[name]
    
    def items(self):
        """Iterate over (name, subgraph) pairs."""
        return self._subgraphs.items()
    
    def __iter__(self):
        """Iterate over subgraph names."""
        return iter(self._subgraphs.keys())
    
    def __contains__(self, name: str) -> bool:
        """Check if a subgraph name is registered."""
        return name in self._subgraphs
    
    def __len__(self) -> int:
        """Number of registered subgraphs."""
        return len(self._subgraphs)
