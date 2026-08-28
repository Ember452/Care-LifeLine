from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from care_lifeline.config import get_settings
from care_lifeline.tools.rag.chunker import Chunk
from care_lifeline.tools.rag.embeddings import EmbeddingPort, LocalEmbedding, MockEmbedding
from care_lifeline.tools.rag.index_builder import build_index
from care_lifeline.tools.rag.reranker import CrossEncoderReranker, MockReranker, Reranker
from care_lifeline.tools.rag.retriever import HybridRetriever, SimpleBM25
from care_lifeline.tools.rag.store import MemoryVectorStore, VectorStore

_GUIDELINE_DIR = Path(__file__).resolve().parents[4] / "data" / "guidelines"


def _make_embedding() -> EmbeddingPort:
    settings = get_settings()
    if settings.rag_enabled:
        return LocalEmbedding()
    return MockEmbedding()


def _make_store(embedding: EmbeddingPort) -> VectorStore:
    settings = get_settings()
    if settings.qdrant_url:
        from qdrant_client import QdrantClient

        from care_lifeline.tools.rag.qdrant_store import QdrantVectorStore

        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        return QdrantVectorStore(client, settings.rag_collection, embedding.dim, embedding)
    return MemoryVectorStore(embedding.dim)


@lru_cache
def build_report_retriever() -> tuple[HybridRetriever, Reranker, list[Chunk]] | None:
    """Lazily build the guideline retriever used by report interpretation.

    Returns ``None`` when no guideline corpus is present (or the configured
    backend is unreachable), so callers fall back to the static citation.
    Backend (Qdrant vs in-memory) and embedding (real vs mock) are from settings.
    """
    if not _GUIDELINE_DIR.exists():
        return None
    try:
        settings = get_settings()
        embedding = _make_embedding()
        store = _make_store(embedding)
        bm25 = SimpleBM25()
        chunks = build_index(_GUIDELINE_DIR, store, embedding, bm25)
        if not chunks:
            return None
        # real 模式（rag_enabled）启用 cross-encoder 精排；mock 用保序精排保持零依赖。
        reranker: Reranker = CrossEncoderReranker() if settings.rag_enabled else MockReranker()
        return HybridRetriever(store, embedding, bm25, k=5), reranker, chunks
    except Exception:  # backend/embedding unavailable -> degrade to static citation
        return None
