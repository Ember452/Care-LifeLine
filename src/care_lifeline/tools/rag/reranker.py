from __future__ import annotations

from abc import ABC, abstractmethod

from care_lifeline.tools.rag.chunker import Chunk


class Reranker(ABC):
    """Re-rank retrieved chunks given the query."""

    @abstractmethod
    def rerank(self, query: str, chunks: list[Chunk]) -> list[Chunk]:
        ...


class MockReranker(Reranker):
    """Order-preserving reranker for tests/offline runs."""

    def rerank(self, query: str, chunks: list[Chunk]) -> list[Chunk]:
        return chunks


class CrossEncoderReranker(Reranker):
    """Real cross-encoder reranker (sentence-transformers), enabled only in prod."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, chunks: list[Chunk]) -> list[Chunk]:
        if not chunks:
            return []
        pairs = [(query, chunk.text) for chunk in chunks]
        scores = self._model.predict(pairs)
        order = sorted(range(len(chunks)), key=lambda i: -float(scores[i]))
        return [chunks[i] for i in order]
