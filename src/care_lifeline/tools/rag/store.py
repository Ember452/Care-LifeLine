from __future__ import annotations

from abc import ABC, abstractmethod

from care_lifeline.tools.rag.chunker import Chunk


class VectorStore(ABC):
    """Abstraction over a vector backend (in-memory or Qdrant)."""

    @abstractmethod
    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(self, vector: list[float], top_k: int = 5) -> list[tuple[Chunk, float]]:
        ...


class MemoryVectorStore(VectorStore):
    """In-memory cosine vector store; keeps RAG testable without Qdrant."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._items: list[tuple[Chunk, list[float]]] = []

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._items.append((chunk, vector))

    def search(self, vector: list[float], top_k: int = 5) -> list[tuple[Chunk, float]]:
        scored = [(chunk, self._cosine(vector, vec)) for chunk, vec in self._items]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)
