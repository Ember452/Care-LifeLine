from qdrant_client import QdrantClient

from care_lifeline.tools.rag.chunker import Chunk
from care_lifeline.tools.rag.embeddings import MockEmbedding
from care_lifeline.tools.rag.qdrant_store import QdrantVectorStore


def test_qdrant_store_add_and_search_roundtrip() -> None:
    client = QdrantClient(location=":memory:")
    store = QdrantVectorStore(client, "ut_guidelines", 64, MockEmbedding())
    chunks = [Chunk(text="高血压目标 <140/90 mmHg", index=0, source="高血压管理指南")]
    store.add(chunks, [[1.0] + [0.0] * 63])

    hits = store.search([1.0] + [0.0] * 63, top_k=3)
    assert hits
    assert "高血压" in hits[0][0].text
    assert hits[0][0].source == "高血压管理指南"
