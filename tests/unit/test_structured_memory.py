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
    assert active.valid_to is None  # 当前有效
    patient_memory.append_medication(1, "阿司匹林")

    assert len(patient_memory.list_medications(1, active_only=True)) == 2

    assert patient_memory.stop_medication(active.id) is True
    assert patient_memory.stop_medication(active.id) is False  # 已失效不可重复失效
    assert patient_memory.stop_medication(9999) is False
    remaining = patient_memory.list_medications(1, active_only=True)
    assert [m.name for m in remaining] == ["阿司匹林"]
    # 停药不删行：历史切片仍可追溯，且 valid_to 已关闭
    history = patient_memory.list_medications(1, active_only=False, include_history=True)
    assert [m.name for m in history] == ["华法林", "阿司匹林"]
    assert history[0].valid_to is not None


def test_medication_provenance_roundtrip() -> None:
    row = patient_memory.append_medication(
        1, "布洛芬", provenance="extracted", source_session_id=42
    )
    assert row.provenance == "extracted"
    assert row.source_session_id == 42
    stored = patient_memory.list_medications(1)[0]
    assert stored.provenance == "extracted"


def test_allergy_append_deactivate_and_list() -> None:
    patient_memory.append_allergy(1, "青霉素", "皮疹", "severe")
    penicillin = patient_memory.list_allergies(1)[0]
    patient_memory.append_allergy(1, "花粉")
    allergies = patient_memory.list_allergies(1)
    assert len(allergies) == 2
    assert allergies[0].severity == "severe"
    assert allergies[1].reaction is None

    # 误报失效：当前切片不再返回，历史保留
    assert patient_memory.deactivate_allergy(penicillin.id) is True
    assert patient_memory.deactivate_allergy(penicillin.id) is False
    current = patient_memory.list_allergies(1, active_only=True)
    assert [a.allergen for a in current] == ["花粉"]
    history = patient_memory.list_allergies(1, active_only=False)
    assert [a.allergen for a in history] == ["青霉素", "花粉"]
    assert history[0].valid_to is not None


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


def test_memory_staleness_reminders(monkeypatch) -> None:
    """超龄在用药物/过敏生成复核提醒；新鲜记录与关闭开关时不生成。"""
    from care_lifeline.proactive.trigger import memory_staleness_reminders

    old = patient_memory.append_medication(1, "华法林", provenance="clinician")
    patient_memory.append_medication(1, "布洛芬")
    patient_memory.append_allergy(1, "青霉素", severity="severe")
    # 手工把「华法林」与「青霉素」的 valid_from 拨回到 200 天前
    from datetime import datetime, timedelta

    from care_lifeline.db.engine import get_sessionmaker

    maker = get_sessionmaker()
    with maker() as session:
        from care_lifeline.db.models import PatientAllergy, PatientMedication

        old_row = session.get(PatientMedication, old.id)
        old_row.valid_from = datetime.now() - timedelta(days=200)
        allergy_row = session.get(PatientAllergy, 1)
        allergy_row.valid_from = datetime.now() - timedelta(days=200)
        session.commit()

    monkeypatch.setenv("CARE_MEMORY_REVIEW_DAYS", "180")
    get_settings.cache_clear()
    reminders = memory_staleness_reminders(1)
    metrics = [r.metric for r in reminders]
    assert metrics == ["用药:华法林", "过敏:青霉素"]  # 新鲜的布洛芬不提醒
    assert reminders[0].severity == "info"
    assert "请确认" in reminders[0].message

    # 关闭开关：不生成
    monkeypatch.setenv("CARE_MEMORY_REVIEW_DAYS", "0")
    get_settings.cache_clear()
    assert memory_staleness_reminders(1) == []
    get_settings.cache_clear()
