from care_lifeline.tools.rag.registry import build_report_retriever


def test_report_retriever_built_from_guidelines() -> None:
    bundle = build_report_retriever()
    assert bundle is not None
    retriever, _reranker, chunks = bundle
    assert chunks
    hits = retriever.retrieve("高血压患者的降压目标是多少", k=3)
    assert hits
    assert any("高血压" in chunk.text for chunk in hits)
