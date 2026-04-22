from langgraph.graph import END, START, StateGraph
from abc import ABC, abstractmethod
from typing import Dict, List

from core.protocols import ToolProtocol
from core.state import SubgraphState

class RetrieverBase(ABC):
    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Retrieve documents for query."""
        raise NotImplementedError

    @abstractmethod
    async def ingest(self, documents: List[Dict]) -> None:
        """Ingest documents into index."""
        raise NotImplementedError


class DummyRetriever(RetrieverBase):
    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        return []

    async def ingest(self, documents: List[Dict]) -> None:
        return None

class RAGTool(ToolProtocol):

    name = "RAG_tool"

    def describe(self):
        return """
        RAG tool (not implemented)
        """
    
    async def RAG_node(self, state: SubgraphState):
        inputs = state["common_tool_input"]["args"]
        
        if inputs.get("retriever_type") == "dummy":
            retriever = DummyRetriever()
        elif inputs.get("retriever_type") == "base":
            retriever = RetrieverBase()
        else: # Default
            retriever = DummyRetriever()

        if inputs.get("action") == "retrieve":
            try:
                output = await retriever.retrieve(inputs.get("query"), inputs.get("top_k", 5))
            except Exception as e:
                state["error"] = str(e)
                state["nextNode"] = state["common_tool_input"]["nextNode"]
                state["common_tool_output"] = {
                    "error": True,
                    "answer": None
                }
                return state
        elif inputs.get("action") == "ingest":
            try:
                output = await retriever.ingest(inputs.get("documents"))
            except Exception as e:
                state["error"] = str(e)
                state["nextNode"] = state["common_tool_input"]["nextNode"]
                state["common_tool_output"] = {
                    "error": True,
                    "answer": None
                }
                return state
        else:
            state["error"] = "invalid action for RAG tool"
            state["nextNode"] = state["common_tool_input"]["nextNode"]
            state["common_tool_output"] = {
                "error": True,
                "answer": None
            }
            return state

        print("[RAG_TOOL] debug : output :", output)
        state["nextNode"] = state["common_tool_input"]["nextNode"]
        state["common_tool_output"] = {
            "answer": output
        }
        return state

    def build(self):
        g = StateGraph(SubgraphState)
        g.add_node("RAG", self.RAG_node)
        g.add_edge(START, "RAG")
        g.add_edge("RAG", END)
        return g.compile()