"""
Subgraph registry for automatic intent routing.

The registry collects all subgraphs at startup. The intent_router
uses their describe() strings to build a dynamic routing table.
"""
from typing import Dict

from core.protocols import SubgraphProtocol, ToolProtocol

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

class CommonToolRegistry:
    """
    Registry for Layer 3 Common Tools.
    
    Common Tools are registered at startup, and can be used by any Subgraph.
    """

    def __init__(self):
        self._commonTools: Dict[str, ToolProtocol] = {}

    def register(self, tool: ToolProtocol) -> None:
        """
        Register a common tool.
        
        Args:
            tool: tool implementing ToolProtocol
        """
        if not hasattr(tool, 'name') or not tool.name:
            raise ValueError(f"Tool must have a 'name' attribute: {tool}")
        
        if not hasattr(tool, 'describe') or not callable(tool.describe):
            raise ValueError(f"Subgraph must implement 'describe()' method: {tool}")
        
        if not hasattr(tool, 'build') or not callable(tool.build):
            raise ValueError(f"Subgraph must implement 'build()' method: {tool}")
        
        self._commonTools[tool.name] = tool
        print(f"✓ Registered subgraph: {tool.name} - {tool.describe()}")

    def get(self, name: str) -> ToolProtocol:
        """Get a tool by name."""
        return self._commonTools[name]

    def items(self):
        """Iterate over (name, tool) pairs."""
        return self._commonTools.items()
    
    def __iter__(self):
        """Iterate over tools names."""
        return iter(self._commonTools.keys())
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool name is registered."""
        return name in self._commonTools
    
    def __len__(self) -> int:
        """Number of registered tools."""
        return len(self._commonTools)