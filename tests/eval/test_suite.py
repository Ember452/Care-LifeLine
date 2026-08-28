from __future__ import annotations

from care_lifeline.eval.suite import run_suite


def test_run_suite_produces_metrics(tmp_path) -> None:
    report_path = str(tmp_path / "eval_report.md")
    out = run_suite(report_path=report_path)

    assert set(out["metrics"]) == {
        "refusal_rate",
        "safety_rate",
        "hitl_rate",
        "compliance",
        "faithfulness",
        "p95_ms",
    }
    # redteam/refusal trigger the safety net on explicit medical off-scope keywords
    assert out["metrics"]["refusal_rate"] > 0.0
    # report cases always carry guideline citations in mock mode
    assert out["metrics"]["faithfulness"] > 0.0
    assert "Care-LifeLine 评测报告" in out["report"]
    with open(report_path, encoding="utf-8") as f:
        assert "refusal_rate" in f.read()
