from __future__ import annotations

import tempfile
from pathlib import Path

from care_lifeline.tools.rag.embeddings import MockEmbedding
from care_lifeline.tools.rag.index_builder import build_index
from care_lifeline.tools.rag.retriever import HybridRetriever, SimpleBM25
from care_lifeline.tools.rag.store import MemoryVectorStore
from care_lifeline.tools.report_interpreter import MockReportInterpreter

SAMPLE = "血压：150/95 mmHg（参考 90-140）\n血糖：7.8 mmol/L（参考 3.9-6.1）偏高\n尿蛋白：阴性"


def test_mock_extract_fields() -> None:
    result = MockReportInterpreter().interpret(SAMPLE)
    names = {f.name for f in result.fields}
    assert "血压" in names and "血糖" in names and "尿蛋白" in names


def test_mock_flags_abnormal_only_when_keyword() -> None:
    result = MockReportInterpreter().interpret(SAMPLE)
    by_name = {f.name: f for f in result.fields}
    assert by_name["血糖"].abnormal is True
    assert by_name["尿蛋白"].abnormal is False


def test_mock_parses_reference_range() -> None:
    result = MockReportInterpreter().interpret(SAMPLE)
    bp = next(f for f in result.fields if f.name == "血压")
    assert bp.reference == "90-140"


def test_mock_returns_citations_when_retriever_provided() -> None:
    with tempfile.TemporaryDirectory() as d:
        Path(d, "g.md").write_text(
            "# 高血压\n收缩压≥140 可诊断高血压。目标<140/90。", encoding="utf-8"
        )
        store = MemoryVectorStore(dim=32)
        bm25 = SimpleBM25()
        build_index(d, store, MockEmbedding(dim=32), bm25)
        retriever = HybridRetriever(store, MockEmbedding(dim=32), bm25)
        result = MockReportInterpreter().interpret("血压150", retriever)
        assert result.citations
        assert any("高血压" in c.snippet for c in result.citations)


def test_mock_one_line_multiple_metrics_parses_all() -> None:
    # P1-11：一行多指标必须全部解析出来（之前只解析第一个）。
    text = "血压：150/95 mmHg（参考 90-140），空腹血糖：7.8 mmol/L（参考 3.9-6.1）偏高"
    result = MockReportInterpreter().interpret(text)
    by_name = {f.name: f for f in result.fields}
    assert set(by_name) == {"血压", "空腹血糖"}
    assert by_name["空腹血糖"].abnormal is True
    assert by_name["血压"].reference == "90-140"


def test_citation_has_real_source_rejects_placeholder() -> None:
    from care_lifeline.graph.state import Citation
    from care_lifeline.tools.report_interpreter import citation_has_real_source

    assert (
        citation_has_real_source(Citation(index=0, source="hypertension.md", snippet="x")) is True
    )
    assert citation_has_real_source({"source": "diabetes.md", "snippet": "y"}) is True
    assert citation_has_real_source(Citation(index=0, source="临床检验指南", snippet="x")) is False
    assert citation_has_real_source({"source": "", "snippet": "y"}) is False
    assert citation_has_real_source({"snippet": "y"}) is False
