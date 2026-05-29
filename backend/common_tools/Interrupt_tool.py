from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from typing import Optional, TypedDict, Dict
from langchain_core.messages import AIMessage, HumanMessage

from core.protocols import ToolProtocol
from core.state import SubgraphState

class InterruptArg(TypedDict, total=False): # TODO : redefined it
    event_name: str # name of interrupt event. default is "interrupt"
    text: Optional[str] # question to ask
    prompt_id: str
    step: Optional[int]
    input_type: Optional[str]
    can_skip: bool
    other_data: Optional[Dict]

class InterruptTool(ToolProtocol):

    """
    Interrupt tool to get user input from inside a subGraph

    NOTE : This tool writes into the core property "messages"
    """
    
    name = "Interrupt_tool"
    
    def describe(self):
        return """
        Interrupt any graph to get a user's answer. Resume at the step in which the interrupt node occured.
        """

    def wrapped_interrupt(self, state: SubgraphState) -> SubgraphState:
        # TODO ?: maybe add a bool property in args to decide wether to add interrupt messages in the core message file or not
        args : InterruptArg = state["common_tool_input"]["args"]
        answer = interrupt(args)
        text = None
        if isinstance(answer, dict):
            text = str(answer.get("text", "")).strip()
        else:
            text = str(answer)
        print("answer :", answer)
        state["nextNode"] = state["common_tool_input"]["nextNode"]
        state["common_tool_output"] = {
            "answer": answer
        }
        state["messages"].append(HumanMessage(content=answer["text"]))
        return state

    def build(self):
        g = StateGraph(SubgraphState)
        g.add_node("interrupt", self.wrapped_interrupt)
        g.add_edge(START, "interrupt")
        g.add_edge("interrupt", END)
        return g.compile()