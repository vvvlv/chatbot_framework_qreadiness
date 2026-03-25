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
from tools.quantum_analyzer.tool import QuantumAnalyzerTool
from tools.quantum_data_collector.tool import QuantumDataCollectorTool
from tools.quantum_presenter.tool import QuantumPresenterTool


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
        data_collector: QuantumDataCollectorTool,
        analyzer: QuantumAnalyzerTool,
        presenter: QuantumPresenterTool,
    ):
        self._collector = data_collector
        self._analyzer = analyzer
        self._presenter = presenter
    
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
        
        # Add tool nodes
        g.add_node("collector", self._collector.build())
        g.add_node("collector_to_analyzer", self._collector_to_analyzer)
        g.add_node("analyzer", self._analyzer.build())
        g.add_node("analyzer_to_presenter", self._analyzer_to_presenter)
        g.add_node("presenter", self._presenter.build())
        
        # Flow: collector -> analyzer -> presenter
        g.add_edge(START, "collector")
        g.add_conditional_edges("collector", self._after_collector, {
            "collector_to_analyzer": "collector_to_analyzer",
            # Continue collector path; if node interrupts, LangGraph suspends the run.
            "collector": "collector",
            END: END,
        })
        g.add_edge("collector_to_analyzer", "analyzer")
        g.add_conditional_edges("analyzer", self._after_analyzer, {
            "analyzer_to_presenter": "analyzer_to_presenter",
            END: END,
        })
        g.add_edge("analyzer_to_presenter", "presenter")
        g.add_edge("presenter", END)
        
        return g.compile()

    @staticmethod
    async def _collector_to_analyzer(state: SubgraphState) -> SubgraphState:
        """Copy collector output into tool_input for analyzer."""
        tool_output = state.get("tool_output", {}) or {}
        step_data = tool_output.get("step_data", {})
        state["tool_input"] = {"step_data": step_data}
        # Clear stale tool-local payloads before entering next tool.
        state["step_data"] = {}
        state["is_complete"] = False
        state["error"] = None
        state["tool_status"] = "running"
        return state

    @staticmethod
    async def _analyzer_to_presenter(state: SubgraphState) -> SubgraphState:
        """Copy analyzer output into tool_input for presenter."""
        tool_output = state.get("tool_output", {}) or {}
        step_data = tool_output.get("step_data", {})
        state["tool_input"] = {"step_data": step_data}
        # Clear stale tool-local payloads before entering next tool.
        state["step_data"] = {}
        state["is_complete"] = False
        state["error"] = None
        state["tool_status"] = "running"
        return state
    
    @staticmethod
    def _after_collector(state: SubgraphState) -> str:
        """
        Route after data collection completes.
        
        If tool completed successfully, move to analyzer.
        If error, end subgraph.
        If tool is suspended (interrupt), it will be resumed on next API call.
        """
        tool_status = state.get("tool_status", "idle")
        tool_output = state.get("tool_output", {})
        is_complete = tool_output and tool_output.get("is_complete")
        
        print(f"[QUANTUM_SUBGRAPH] After collector - tool_status: {tool_status}, is_complete: {is_complete}")
        
        if tool_status == "error":
            print("[QUANTUM_SUBGRAPH] ✗ Collector error, ending subgraph")
            return END
        
        # Check if collector tool is complete
        if is_complete:
            print("[QUANTUM_SUBGRAPH] ✓ Collector complete, routing to analyzer")
            return "collector_to_analyzer"
        
        # If tool is still running (suspended at interrupt), stay in collector
        print("[QUANTUM_SUBGRAPH] Collector still running (suspended), staying in collector")
        return "collector"
    
    @staticmethod
    def _after_analyzer(state: SubgraphState) -> str:
        """
        Route after analyzer completes.
        
        Pass analyzer output to presenter.
        """
        tool_output = state.get("tool_output", {})
        is_complete = tool_output and tool_output.get("is_complete")
        
        print(f"[QUANTUM_SUBGRAPH] After analyzer - is_complete: {is_complete}")
        
        if is_complete:
            print("[QUANTUM_SUBGRAPH] ✓ Analyzer complete, routing to presenter")
            return "analyzer_to_presenter"
        
        print("[QUANTUM_SUBGRAPH] Analyzer not complete, ending subgraph")
        return END
