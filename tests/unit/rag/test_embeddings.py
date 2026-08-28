from __future__ import annotations

from care_lifeline.tools.rag.embeddings import MockEmbedding


def test_mock_embedding_deterministic_and_normalized() -> None:
    emb = MockEmbedding(dim=32)
    a = emb.embed(["高血压目标值"])
    b = emb.embed(["高血压目标值"])
    assert a == b
    assert len(a[0]) == 32
    norm = sum(x * x for x in a[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_mock_embedding_distinguishes_texts() -> None:
    emb = MockEmbedding(dim=32)
    a, b = emb.embed(["高血压", "糖尿病"])
    assert a != b
