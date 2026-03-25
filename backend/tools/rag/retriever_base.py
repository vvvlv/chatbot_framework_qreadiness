"""
RetrieverBase abstraction for RAG (lives with tools).
"""
from abc import ABC, abstractmethod
from typing import Dict, List


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

