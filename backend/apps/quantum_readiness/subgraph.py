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
        g.add_node("before_collector", self._before_collector)
        g.add_node("collector", self._collector.build())
        g.add_node("after_collector", self._after_collector_adapter)
        g.add_node("collector_to_analyzer", self._collector_to_analyzer)
        g.add_node("before_analyzer", self._before_analyzer)
        g.add_node("analyzer", self._analyzer.build())
        g.add_node("after_analyzer", self._after_analyzer_adapter)
        g.add_node("analyzer_to_presenter", self._analyzer_to_presenter)
        g.add_node("before_presenter", self._before_presenter)
        g.add_node("presenter", self._presenter.build())
        g.add_node("after_presenter", self._after_presenter_adapter)
        
        # Flow: collector -> analyzer -> presenter
        g.add_edge(START, "before_collector")
        g.add_edge("before_collector", "collector")
        g.add_edge("collector", "after_collector")
        g.add_conditional_edges("after_collector", self._after_collector, {
            "collector_to_analyzer": "collector_to_analyzer",
            # Continue collector path; if node interrupts, LangGraph suspends the run.
            "collector": "before_collector",
            END: END,
        })
        g.add_edge("collector_to_analyzer", "before_analyzer")
        g.add_edge("before_analyzer", "analyzer")
        g.add_edge("analyzer", "after_analyzer")
        g.add_conditional_edges("after_analyzer", self._after_analyzer, {
            "analyzer_to_presenter": "analyzer_to_presenter",
            END: END,
        })
        g.add_edge("analyzer_to_presenter", "before_presenter")
        g.add_edge("before_presenter", "presenter")
        g.add_edge("presenter", "after_presenter")
        g.add_edge("after_presenter", END)
        
        return g.compile()

    @staticmethod
    async def _before_collector(state: SubgraphState) -> SubgraphState:
        state["active_tool"] = "quantum_data_collector"
        state["tool_status"] = "running"
        return state

    @staticmethod
    async def _after_collector_adapter(state: SubgraphState) -> SubgraphState:
        tool_result = state.get("tool_result", {}) or {}
        state["pending_prompt_id"] = state.get("pending_prompt_id")
        if tool_result:
            state["tool_output"] = tool_result
            if tool_result.get("error"):
                state["tool_status"] = "error"
            elif tool_result.get("is_complete"):
                state["tool_status"] = "done"
        return state

    @staticmethod
    async def _collector_to_analyzer(state: SubgraphState) -> SubgraphState:
        """Copy collector output into tool_input for analyzer."""
        tool_output = state.get("tool_output", {}) or {}
        step_data = tool_output.get("step_data", {})
        state["tool_input"] = {"step_data": step_data}
        # Clear stale tool-local payloads before entering next tool.
        state["step_data"] = {}
        state["tool_result"] = {}
        state["is_complete"] = False
        state["error"] = None
        state["tool_status"] = "running"
        return state

    @staticmethod
    async def _before_analyzer(state: SubgraphState) -> SubgraphState:
        state["active_tool"] = "quantum_analyzer"
        state["tool_status"] = "running"
        return state

    @staticmethod
    async def _after_analyzer_adapter(state: SubgraphState) -> SubgraphState:
        tool_result = state.get("tool_result", {}) or {}
        if tool_result:
            state["tool_output"] = tool_result
            if tool_result.get("error"):
                state["tool_status"] = "error"
            elif tool_result.get("is_complete"):
                state["tool_status"] = "done"
        return state

    @staticmethod
    async def _analyzer_to_presenter(state: SubgraphState) -> SubgraphState:
        """Copy analyzer output into tool_input for presenter."""
        tool_output = state.get("tool_output", {}) or {}
        step_data = tool_output.get("step_data", {})
        state["tool_input"] = {"step_data": step_data}
        # Clear stale tool-local payloads before entering next tool.
        state["step_data"] = {}
        state["tool_result"] = {}
        state["is_complete"] = False
        state["error"] = None
        state["tool_status"] = "running"
        return state

    @staticmethod
    async def _before_presenter(state: SubgraphState) -> SubgraphState:
        state["active_tool"] = "quantum_presenter"
        state["tool_status"] = "running"
        return state

    @staticmethod
    async def _after_presenter_adapter(state: SubgraphState) -> SubgraphState:
        tool_result = state.get("tool_result", {}) or {}
        if tool_result:
            state["tool_output"] = tool_result
            if tool_result.get("error"):
                state["tool_status"] = "error"
            elif tool_result.get("is_complete"):
                state["tool_status"] = "done"
        state["active_tool"] = None
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
        tool_output = state.get("tool_output", {}) or {}
        is_complete = bool(tool_output.get("is_complete"))
        
        print(f"[QUANTUM_SUBGRAPH] After collector - tool_status: {tool_status}, is_complete: {is_complete}")
        
        if tool_status == "error":
            print("[QUANTUM_SUBGRAPH] ✗ Collector error, ending subgraph")
            return END
        
        # Check if collector tool is complete
        if tool_status == "done" or is_complete:
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
