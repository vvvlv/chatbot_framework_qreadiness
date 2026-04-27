"""
Quantum Readiness Subgraph - Layer 2 use-case subgraph.

Orchestrates three Layer 3 tools:
1. QuantumDataCollectorTool - collects information via conversational questioning
2. QuantumAnalyzerTool - calculates scores and determines archetype
3. QuantumPresenterTool - formats results and generates report
"""

from langgraph.graph import END, START, StateGraph

from core.protocols import SubgraphProtocol
from core.state import SubgraphState
from core.registry import CommonToolRegistry
from core.model_gateway import ModelGateway

# App subgraphs
from apps.quantum_readiness.subgraphs.quantum_analyzer.tool import QuantumAnalyzerTool
from apps.quantum_readiness.subgraphs.quantum_data_collector.tool import QuantumDataCollectorTool
from apps.quantum_readiness.subgraphs.quantum_presenter.tool import QuantumPresenterTool

class QuantumReadinessSubgraph(SubgraphProtocol):
    """
    Quantum Readiness assessment subgraph (Layer 2).
    
    Orchestrates a tool-based workflow:
    1. Data Collection Tool - collects all required information
    2. Analyzer Tool - processes data and calculates scores
    3. Presenter Tool - formats results and generates report
    """
    
    name = "quantum_readiness"
    
    def __init__(
        self,
        commonTools: CommonToolRegistry,
        model_gateway: ModelGateway
    ):
        self._commonTools = commonTools
        self._model_gateway = model_gateway
    
    def describe(self) -> str:
        """
        Description used by intent_router for automatic routing.
        """
        return (
            "Assess a company's quantum readiness through a structured "
            "conversational workflow evaluating cryptographic risk and "
            "quantum opportunity potential. Guides users through multi-step "
            "assessment with adaptive questioning."
        )
    
    def build(self):
        """
        Build and return the compiled Quantum Readiness subgraph.
        
        Orchestrates the three tools in sequence:
        collector -> analyzer -> presenter
        """
        g = StateGraph(SubgraphState)

        # Import App tools
        data_collector_node = QuantumDataCollectorTool(
            self._model_gateway,
            self._commonTools._commonTools["Interrupt_tool"]
        )
        analyzer_node = QuantumAnalyzerTool(
            self._model_gateway
        )
        presenter_node = QuantumPresenterTool(
            self._model_gateway,
            self._commonTools._commonTools["RAG_tool"]
        )
        
        # Add tool nodes
        g.add_node("data_collector", data_collector_node.build())
        g.add_node("analyzer", analyzer_node.build())
        g.add_node("presenter", presenter_node.build())
        
        # Add edges
        g.add_edge(START, "data_collector")
        g.add_conditional_edges("data_collector", self.router, {
            "analyzer": "analyzer",
            END: END
        })
        g.add_edge("analyzer", "presenter")
        g.add_edge("presenter", END)
        
        return g.compile()

# --------------------- Router (/!\ to not change) ---------------------------

    async def router(self, state: SubgraphState) -> str:
        # TODO: manage errors + manage undefined nextNode
        print("[ROUTER]: debug nextNode : ", state.get("nextNode"))
        return state.get("nextNode")