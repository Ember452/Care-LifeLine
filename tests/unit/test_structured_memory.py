"""结构化纵向记忆（用药史/过敏史/随访计划，文档 §7.4）的行为测试。"""

from datetime import datetime

import pytest

from care_lifeline.config import get_settings
from care_lifeline.db.engine import init_db, reset_state_for_testing
from care_lifeline.graph.nodes.memory import memory_recall_node
from care_lifeline.graph.state import AgentState
from care_lifeline.memory import patient_memory


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/memory.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    yield


def test_medication_append_list_and_stop() -> None:
    active = patient_memory.append_medication(1, "华法林", "2.5mg", "每日一次")
    assert active.status == "active"
    patient_memory.append_medication(1, "阿司匹林")

    assert len(patient_memory.list_medications(1, active_only=True)) == 2

    assert patient_memory.stop_medication(active.id) is True
    assert patient_memory.stop_medication(9999) is False
    remaining = patient_memory.list_medications(1, active_only=True)
    assert [m.name for m in remaining] == ["阿司匹林"]


def test_allergy_append_and_list() -> None:
    patient_memory.append_allergy(1, "青霉素", "皮疹", "severe")
    patient_memory.append_allergy(1, "花粉")
    allergies = patient_memory.list_allergies(1)
    assert len(allergies) == 2
    assert allergies[0].severity == "severe"
    assert allergies[1].reaction is None


def test_followup_add_list_and_complete() -> None:
    due = datetime(2026, 9, 15, 10, 0)
    patient_memory.add_followup(1, "复查肝功能", due)
    patient_memory.add_followup(1, "监测血压")

    pending = patient_memory.list_followups(1, pending_only=True)
    assert len(pending) == 2

    assert patient_memory.complete_followup(pending[0].id) is True
    assert patient_memory.complete_followup(9999) is False
    remaining = patient_memory.list_followups(1, pending_only=True)
    assert [f.plan for f in remaining] == ["监测血压"]


def test_structured_summary_sections() -> None:
    patient_memory.append_medication(1, "华法林", "2.5mg", "每日一次")
    patient_memory.append_allergy(1, "青霉素", "皮疹", "severe")
    patient_memory.add_followup(1, "复查 INR")
    summary = patient_memory.structured_summary(1)
    assert "正在用药：华法林（2.5mg，每日一次）" in summary
    assert "过敏史：青霉素（severe）：皮疹" in summary
    assert "待办随访：复查 INR" in summary
    # 分号连接三个 section
    assert summary.count("；") == 2


def test_structured_summary_empty_is_empty_string() -> None:
    patient_memory.ensure_patient(2)
    assert patient_memory.structured_summary(2) == ""


def test_memory_recall_includes_structured_context() -> None:
    """recall 节点把结构化记忆并进 memory_context（仅有结构化记忆、无指标时也注入）。"""
    patient_memory.append_medication(7, "华法林")
    state: AgentState = {"messages": [], "patient_id": 7}  # type: ignore[typeddict-item]
    out = memory_recall_node(state)
    assert "正在用药：华法林" in out["memory_context"]


def test_memory_recall_empty_without_any_memory() -> None:
    patient_memory.ensure_patient(3)
    state: AgentState = {"messages": [], "patient_id": 3}  # type: ignore[typeddict-item]
    assert memory_recall_node(state) == {}
