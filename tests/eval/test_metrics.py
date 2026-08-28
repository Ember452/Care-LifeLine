from __future__ import annotations

from care_lifeline.eval.metrics import compute_metrics


def test_compute_metrics_refusal_rate() -> None:
    results = [
        {
            "expect": "refuse",
            "blocked": True,
            "hitl": False,
            "has_disclaimer": False,
            "has_citation": False,
        },
        {
            "expect": "refuse",
            "blocked": False,
            "hitl": False,
            "has_disclaimer": False,
            "has_citation": False,
        },
        {
            "expect": "answer",
            "blocked": False,
            "hitl": False,
            "has_disclaimer": True,
            "has_citation": True,
        },
    ]
    metrics = compute_metrics(results)
    assert metrics["refusal_rate"] == 0.5
    assert metrics["safety_rate"] == round(2 / 3, 4)
    assert metrics["compliance"] == round(1 / 3, 4)
    assert metrics["faithfulness"] == round(1 / 3, 4)
    assert metrics["hitl_rate"] == 0.0


def test_compute_metrics_empty_is_zero() -> None:
    metrics = compute_metrics([])
    assert metrics["refusal_rate"] == 0.0
    assert metrics["p95_ms"] == 0.0


def test_p95_latency() -> None:
    results = [
        {
            "blocked": False,
            "hitl": False,
            "has_disclaimer": False,
            "has_citation": False,
            "latency_ms": m,
        }
        for m in (10, 20, 30, 100, 200)
    ]
    assert compute_metrics(results)["p95_ms"] == 200


def test_safety_rate_counts_correct_refusals() -> None:
    # 语义修正：safety_rate = 恰当安全响应占比，而非「未被拦截占比」。
    results = [
        {
            "expect": "refuse",
            "blocked": True,  # 应拒答且已拒答 → 恰当
            "hitl": False,
            "has_disclaimer": False,
            "has_citation": False,
        },
        {
            "expect": "refuse",
            "blocked": True,  # 应拒答且已拒答 → 恰当
            "hitl": False,
            "has_disclaimer": False,
            "has_citation": False,
        },
        {
            "expect": "answer",
            "blocked": True,  # 正常请求被误拦 → 不恰当
            "hitl": False,
            "has_disclaimer": False,
            "has_citation": False,
        },
    ]
    metrics = compute_metrics(results)
    # 旧语义（not blocked）会得到 1/3；新语义应为 2/3。
    assert metrics["safety_rate"] == round(2 / 3, 4)
