from __future__ import annotations

import tempfile
from pathlib import Path

from care_lifeline.tools.rag.chunker import Chunk, chunk_text
from care_lifeline.tools.rag.embeddings import MockEmbedding
from care_lifeline.tools.rag.index_builder import build_index
from care_lifeline.tools.rag.retriever import HybridRetriever, SimpleBM25
from care_lifeline.tools.rag.store import MemoryVectorStore


def _indexed() -> HybridRetriever:
    guideline = (
        "# 高血压\n收缩压 ≥ 140 可诊断高血压。目标值 < 140/90 mmHg。"
        "\n# 糖尿病\n空腹血糖 ≥ 7.0 可诊断糖尿病。"
    )
    with tempfile.TemporaryDirectory() as d:
        Path(d, "g.md").write_text(guideline, encoding="utf-8")
        store = MemoryVectorStore(dim=32)
        bm25 = SimpleBM25()
        build_index(d, store, MockEmbedding(dim=32), bm25)
        return HybridRetriever(store, MockEmbedding(dim=32), bm25, k=3)


def test_hybrid_retriever_recalls_relevant_chunk() -> None:
    retriever = _indexed()
    hits = retriever.retrieve("高血压的诊断标准是什么")
    assert hits
    assert any("高血压" in c.text for c in hits)


def test_hybrid_retriever_respects_k() -> None:
    retriever = _indexed()
    assert len(retriever.retrieve("血压", k=1)) == 1


def test_bm25_lexical_match_ranked() -> None:
    bm25 = SimpleBM25()
    bm25.add(chunk_text("收缩压 ≥ 140 可诊断高血压。", source="g.md"))
    hits = bm25.search("收缩压 诊断", top_k=1)
    assert hits and "收缩压" in hits[0][0].text


def test_store_cosine_search_returns_top() -> None:
    store = MemoryVectorStore(dim=8)
    store.add([Chunk(text="高血压")], [[1.0] + [0.0] * 7])
    hits = store.search([1.0] + [0.0] * 7, top_k=1)
    assert hits and hits[0][0].text == "高血压"
