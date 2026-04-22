from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from core.protocols import ToolProtocol
from core.state import SubgraphState

class InterruptTool(ToolProtocol):

    """
    Interrupt tool to get user input from inside a subGraph
    """
    
    name = "Interrupt_tool"
    
    def describe(self):
        return """
        Interrupt any graph to get a user's answer. Resume at the step in which the interrupt node occured.
        """

    def wrapped_interrupt(self, state: SubgraphState) -> SubgraphState:
        answer = interrupt(state["common_tool_input"]["args"])
        state["nextNode"] = state["common_tool_input"]["nextNode"]
        state["common_tool_output"] = {
            "answer": answer
        }
        return state

    def build(self):
        g = StateGraph(SubgraphState)
        g.add_node("interrupt", self.wrapped_interrupt)
        g.add_edge(START, "interrupt")
        g.add_edge("interrupt", END)
        return g.compile()