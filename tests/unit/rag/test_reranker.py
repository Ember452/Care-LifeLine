from __future__ import annotations

from care_lifeline.tools.rag.chunker import Chunk
from care_lifeline.tools.rag.reranker import MockReranker


def test_mock_reranker_preserves_order() -> None:
    chunks = [Chunk(text="a", index=i) for i in range(3)]
    out = MockReranker().rerank("query", chunks)
    assert [c.index for c in out] == [0, 1, 2]
