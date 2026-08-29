"""指南检索质量评测（eval/retrieval.py）的行为测试。"""

from care_lifeline.eval.retrieval import hit_rank, render_markdown


def test_hit_rank_finds_expected_source() -> None:
    assert hit_rank(["a.md", "b.md", "c.md"], "b.md") == 2
    assert hit_rank(["b.md"], "b.md") == 1
    assert hit_rank(["a.md", "b.md"], "missing.md") is None
    assert hit_rank([], "a.md") is None


def test_render_markdown_includes_metrics_and_misses() -> None:
    details = [
        {"query": "q1", "expect": "a.md", "top_sources": ["a.md"], "rank": 1},
        {"query": "q2", "expect": "b.md", "top_sources": ["c.md"], "rank": None},
    ]
    text = render_markdown(details, hit_at_1=0.5, hit_at_3=0.5, mrr=0.5)
    assert "hit@1" in text and "0.5" in text
    assert "未命中" in text  # 未命中用例显式呈现，不静默
    assert "不进检索索引" in text  # 语料隔离声明


def test_retrieval_eval_runs_on_real_pipeline() -> None:
    """端到端：默认 mock 向量管线上跑通并产出合法指标（回归口径）。"""
    from care_lifeline.eval.retrieval import run_retrieval_eval

    outcome = run_retrieval_eval(report_path="eval_retrieval_test.md")
    try:
        cases = outcome["cases"]
        assert len(cases) >= 15
        assert 0.0 <= outcome["hit_at_1"] <= 1.0
        assert outcome["hit_at_3"] >= outcome["hit_at_1"]  # hit@3 不会低于 hit@1
        assert 0.0 <= outcome["mrr"] <= 1.0
    finally:
        import os

        with open("eval_retrieval_test.md", encoding="utf-8") as f:
            assert "检索质量评测" in f.read()
        os.remove("eval_retrieval_test.md")
