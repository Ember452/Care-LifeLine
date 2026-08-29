"""P1-F / P1-G 回归：纵向记忆接入图 + router LLM 意图兜底。"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from care_lifeline.config import get_settings
from care_lifeline.db.engine import init_db, reset_state_for_testing
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.nodes.memory import memory_recall_node
from care_lifeline.graph.nodes.router import classify_intent
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.memory import patient_memory


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/mem.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    yield
    reset_state_for_testing()


def _state(text: str, patient_id: int | None = None) -> AgentState:
    return {
        "messages": [HumanMessage(text)],
        "patient_id": patient_id,
        "intent": "",
        "risk_level": "routine",
        "scope_result": None,
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[typeddict-item]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
        "retry_count": 0,
        "memory_context": "",
    }


class _FakeRealProvider:
    """模拟 real 模式 provider：complete 返回固定意图词。"""

    def __init__(self, reply: str, fail: bool = False) -> None:
        self._reply = reply
        self._fail = fail
        self.calls = 0

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: str = "strong"
    ) -> str:
        self.calls += 1
        if self._fail:
            raise RuntimeError("llm down")
        return self._reply

    def stream(
        self, *, messages: list[dict], temperature: float = 0.2, tier: str = "strong"
    ) -> object:
        raise NotImplementedError


def test_memory_recall_node_without_patient_returns_empty() -> None:
    assert memory_recall_node(_state("头疼")) == {}


def test_memory_recall_node_without_metrics_returns_empty(db) -> None:
    patient_memory.ensure_patient(7)
    assert memory_recall_node(_state("头疼", patient_id=7)) == {}


def test_memory_recall_node_injects_summary(db) -> None:
    patient_memory.append_metric(7, "收缩压", 140.0, "mmHg")
    patient_memory.append_metric(7, "收缩压", 150.0, "mmHg")
    result = memory_recall_node(_state("头疼", patient_id=7))
    assert "收缩压：最新 150 mmHg" in result["memory_context"]
    assert "上升" in result["memory_context"]


def test_graph_with_patient_id_populates_memory_context(db) -> None:
    """分诊链路经 memory_recall：draft 提示词可见患者纵向指标（P1-F 全链路）。"""
    patient_memory.append_metric(7, "收缩压", 150.0, "mmHg")
    graph = build_graph(MockProvider())
    result = graph.invoke(_state("我有点头疼", patient_id=7))
    assert result["intent"] == "triage"
    assert "收缩压" in result["memory_context"]


def test_graph_without_patient_keeps_memory_context_empty() -> None:
    graph = build_graph(MockProvider())
    result = graph.invoke(_state("我有点头疼"))
    assert result["memory_context"] == ""


def test_classify_intent_real_mode_llm_overrides_keyword(tmp_path, monkeypatch) -> None:
    """P1-G：real 模式下 LLM 分类优先，症状句含「血压」不再误入报告分支。"""
    monkeypatch.setenv("CARE_LLM_MODE", "real")
    get_settings.cache_clear()
    try:
        provider = _FakeRealProvider("triage")
        risk, intent = classify_intent("我最近两天有点头晕，血压偏高，需要注意什么？", provider)
        assert (risk, intent) == ("routine", "triage")
        assert provider.calls == 1
    finally:
        get_settings.cache_clear()


def test_classify_intent_real_mode_llm_failure_falls_back_to_keyword(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CARE_LLM_MODE", "real")
    get_settings.cache_clear()
    try:
        provider = _FakeRealProvider("", fail=True)
        risk, intent = classify_intent("华法林和阿司匹林能一起吃吗", provider)
        # LLM 不可用 → 回落关键词结论
        assert (risk, intent) == ("routine", "medication")
    finally:
        get_settings.cache_clear()


def test_classify_intent_mock_mode_keeps_keyword_determinism() -> None:
    """mock 模式零 LLM 调用，关键词确定性不回归。"""
    provider = _FakeRealProvider("report")
    assert classify_intent("华法林和阿司匹林能一起吃吗", provider) == ("routine", "medication")
    assert provider.calls == 0
    # 急症词永远走确定性规则，即便 real 模式
    monkeypatch_real = _FakeRealProvider("triage")
    assert classify_intent("我现在胸痛得厉害", monkeypatch_real) == ("critical", "emergency")
    assert monkeypatch_real.calls == 0
