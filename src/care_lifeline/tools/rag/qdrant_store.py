from __future__ import annotations

from care_lifeline.tools.rag.chunker import Chunk
from care_lifeline.tools.rag.embeddings import EmbeddingPort
from care_lifeline.tools.rag.store import VectorStore


class QdrantVectorStore(VectorStore):
    """Qdrant-backed vector store (plan: 指南向量检索).

    Implements the same ``add`` / ``search`` surface as ``MemoryVectorStore`` so
    the hybrid retriever is backend-agnostic. A client can be injected for tests
    (e.g. ``QdrantClient(location=":memory:")``); in production it points at the
    Qdrant service configured via ``CARE_QDRANT_URL``.
    """

    def __init__(
        self, client, collection: str, dim: int, embedding: EmbeddingPort
    ) -> None:
        self._client = client
        self._collection = collection
        self._dim = dim
        self._embedding = embedding
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=chunk.index,
                vector=vector,
                payload={"source": chunk.source or "指南", "text": chunk.text},
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self._client.upsert(self._collection, points)

    def search(self, vector: list[float], top_k: int = 5) -> list[tuple[Chunk, float]]:
        response = self._client.query_points(self._collection, query=vector, limit=top_k)
        out: list[tuple[Chunk, float]] = []
        for point in response.points:
            payload = point.payload or {}
            chunk = Chunk(
                index=point.id,
                text=payload.get("text", ""),
                source=payload.get("source") or "指南",
            )
            out.append((chunk, float(point.score)))
        return out
