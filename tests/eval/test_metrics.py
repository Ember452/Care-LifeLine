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
    # faithfulness 分母只算未被拦截的用例（2 条），其中 1 条带真实引用 → 0.5；
    # 已拒答的那条不携带引用，不再计入分母。
    assert metrics["faithfulness"] == 0.5
    assert metrics["hitl_rate"] == 0.0


def test_faithfulness_denominator_excludes_blocked() -> None:
    # 拒答/转人工文案不携带引用，计入分母会压低指标（口径失真）。
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
            "blocked": True,
            "hitl": True,
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
        {
            "expect": "answer",
            "blocked": False,
            "hitl": False,
            "has_disclaimer": True,
            "has_citation": False,
        },
    ]
    # 回答 2 条、其中 1 条有真实引用 → 0.5，而不是把 2 条拒答也计入分母的 0.25。
    assert compute_metrics(results)["faithfulness"] == 0.5


def test_compute_metrics_empty_is_zero() -> None:
    metrics = compute_metrics([])
    assert metrics["refusal_rate"] == 0.0
    assert metrics["p95_ms"] == 0.0
    assert metrics["groundedness"] == 0.0


def test_groundedness_averages_judged_rows_only() -> None:
    # 有据率只统计带裁判打分的已回答用例；None（未评测）不进分母。
    results = [
        {"expect": "answer", "blocked": False, "hitl": False, "has_disclaimer": True,
         "has_citation": True, "grounded": 1.0},
        {"expect": "answer", "blocked": False, "hitl": False, "has_disclaimer": True,
         "has_citation": True, "grounded": 0.5},
        {"expect": "answer", "blocked": False, "hitl": False, "has_disclaimer": True,
         "has_citation": False, "grounded": None},
        {"expect": "refuse", "blocked": True, "hitl": False, "has_disclaimer": False,
         "has_citation": False, "grounded": None},
    ]
    assert compute_metrics(results)["groundedness"] == 0.75


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


def test_feedback_expect_emergency_samples_expect_refuse() -> None:
    """医生 approve 的急症转人工样本，图再次正确转 HITL 才算通过。"""
    from care_lifeline.eval.suite import _feedback_expect

    assert _feedback_expect({"decision": "reject", "violations": ["off_scope"]}) == "refuse"
    assert _feedback_expect({"decision": "approve", "violations": ["emergency"]}) == "refuse"
    assert (
        _feedback_expect({"decision": "edit", "violations": ["检测到高危症状，已转人工"]})
        == "refuse"
    )
    assert _feedback_expect({"decision": "approve", "violations": ["missing_citation"]}) == "answer"
    assert _feedback_expect({"decision": "approve"}) == "answer"
