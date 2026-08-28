from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    """Embeddings abstraction; mock for tests, SentenceTransformer for real use."""

    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class MockEmbedding(EmbeddingPort):
    """Deterministic, dependency-free embedding for tests/offline runs."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for i, ch in enumerate(text):
            digest = hashlib.sha256(ch.encode("utf-8")).hexdigest()
            vec[i % self.dim] += (int(digest, 16) % 1000) / 1000.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


class LocalEmbedding(EmbeddingPort):
    """Real embedding via sentence-transformers (only when RAG is enabled)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension() or 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()
