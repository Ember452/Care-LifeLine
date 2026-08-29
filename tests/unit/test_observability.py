"""可观测性链路：provider 用量、节点计时与图级计时采集。"""

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from care_lifeline.api.runtime import reset_runtime_metrics
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.llm.provider import estimate_usage
from care_lifeline.llm.real_provider import RealProvider


@pytest.fixture(autouse=True)
def _clean_metrics():
    reset_runtime_metrics()
    yield
    reset_runtime_metrics()


def test_mock_provider_tracks_estimated_usage() -> None:
    provider = MockProvider()
    assert provider.last_usage is None
    provider.complete(messages=[{"role": "user", "content": "abcd"}])
    usage = provider.last_usage
    assert usage is not None
    assert usage.input_tokens == 2  # len("abcd") // 2
    assert usage.estimated is True
    assert usage.total_tokens == usage.input_tokens + usage.output_tokens


def test_estimate_usage_marks_estimated() -> None:
    usage = estimate_usage("输入内容", "输出内容更长一些")
    assert usage.estimated is True
    assert usage.input_tokens == len("输入内容") // 2
    assert usage.output_tokens == len("输出内容更长一些") // 2


def test_real_provider_tracks_usage_metadata() -> None:
    """usage_metadata 存在时用真实计量；缺失时降级字符估算。"""
    provider = RealProvider.__new__(RealProvider)  # 跳过 __init__（不建网络客户端）
    provider.last_usage = None
    response = SimpleNamespace(
        usage_metadata={"input_tokens": 120, "output_tokens": 45, "total_tokens": 165}
    )
    provider._track_usage(response, "输入文本", "输出文本")
    assert provider.last_usage is not None
    assert (provider.last_usage.input_tokens, provider.last_usage.output_tokens) == (120, 45)
    assert provider.last_usage.estimated is False

    provider._track_usage(None, "输入文本", "输出文本")
    assert provider.last_usage is not None
    assert provider.last_usage.estimated is True
    assert provider.last_usage.output_tokens == len("输出文本") // 2


def _state() -> AgentState:
    return {
        "messages": [HumanMessage("我最近有点头晕")],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
    }


async def _collect_timings() -> set[str]:
    graph = build_graph(MockProvider())
    timed_nodes: set[str] = set()
    async for mode, chunk in graph.astream(_state(), stream_mode=["updates"]):
        if mode != "updates":
            continue
        for node_name, update in chunk.items():
            if isinstance(update, dict) and "perf_node_ms" in update:
                assert update["perf_node_ms"] >= 0.0
                timed_nodes.add(node_name)
    return timed_nodes


def test_all_nodes_report_timing() -> None:
    timed_nodes = asyncio.run(_collect_timings())
    assert {"scope_check", "router", "triage", "qc_review", "responder"} <= timed_nodes
