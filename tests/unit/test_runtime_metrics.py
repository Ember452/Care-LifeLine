"""运行时指标注册表（api/runtime.py）的行为测试。"""

import pytest

from care_lifeline.api.runtime import (
    node_latency_summary,
    p95_latency_ms,
    qc_status_counts,
    record_latency_ms,
    record_node_ms,
    record_qc_status,
    record_token_usage,
    reset_runtime_metrics,
    token_summary,
)
from care_lifeline.llm.provider import TokenUsage


@pytest.fixture(autouse=True)
def _clean_metrics():
    reset_runtime_metrics()
    yield
    reset_runtime_metrics()


def test_latency_p95() -> None:
    for ms in (10, 20, 30, 100, 200):
        record_latency_ms(float(ms))
    assert p95_latency_ms() == 200


def test_node_latency_summary_percentiles() -> None:
    for ms in (10, 20, 30, 100):
        record_node_ms("qc", float(ms))
    record_node_ms("triage", 5.0)
    summary = node_latency_summary()
    assert set(summary) == {"qc", "triage"}
    assert summary["qc"]["count"] == 4
    assert summary["qc"]["p95_ms"] == 100
    assert summary["triage"] == {"count": 1, "p50_ms": 5.0, "p95_ms": 5.0}


def test_qc_status_counts() -> None:
    record_qc_status("passed")
    record_qc_status("passed")
    record_qc_status("hitl")
    assert qc_status_counts() == {"hitl": 1, "passed": 2}


def test_token_usage_accumulates_per_session() -> None:
    record_token_usage("s1", TokenUsage(input_tokens=100, output_tokens=50))
    record_token_usage("s1", TokenUsage(input_tokens=10, output_tokens=5, estimated=True))
    record_token_usage("s2", TokenUsage(input_tokens=7, output_tokens=3))
    summary = token_summary()
    assert summary["total_input_tokens"] == 117
    assert summary["total_output_tokens"] == 58
    assert summary["request_count"] == 3
    assert summary["estimated_request_count"] == 1
    assert summary["sessions"]["s1"] == {
        "input_tokens": 110,
        "output_tokens": 55,
        "estimated": False,  # 任一次真实计量即视为非估算
    }
    assert summary["sessions"]["s2"]["input_tokens"] == 7


def test_session_tokens_bounded() -> None:
    for i in range(210):
        record_token_usage(f"s{i}", TokenUsage(input_tokens=1, output_tokens=1))
    summary = token_summary()
    assert summary["request_count"] == 210
    # 会话明细有界（只展示最近 20 条），全局累计不丢。
    assert len(summary["sessions"]) == 20  # type: ignore[arg-type]


def test_empty_summary_is_zeroed() -> None:
    assert p95_latency_ms() == 0.0
    assert node_latency_summary() == {}
    assert qc_status_counts() == {}
    summary = token_summary()
    assert summary["total_input_tokens"] == 0
    assert summary["request_count"] == 0


def test_token_usage_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    usage = TokenUsage(input_tokens=1, output_tokens=2)
    with pytest.raises(FrozenInstanceError):
        usage.input_tokens = 5  # type: ignore[misc]


def test_session_tokens_reader() -> None:
    from care_lifeline.api.runtime import session_tokens

    assert session_tokens("none") == 0
    record_token_usage("s1", TokenUsage(input_tokens=30, output_tokens=12))
    assert session_tokens("s1") == 42
