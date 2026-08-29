from __future__ import annotations

import pytest

from care_lifeline.config import get_settings
from care_lifeline.db.engine import init_db, reset_state_for_testing
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


def test_append_and_trend(db) -> None:
    patient_memory.append_metric(1, "收缩压", 150.0, "mmHg")
    patient_memory.append_metric(1, "收缩压", 145.0, "mmHg")
    trend = patient_memory.get_trend(1, "收缩压")
    assert [m.value for m in trend] == [150.0, 145.0]
    assert patient_memory.latest_value(1, "收缩压") == 145.0


def test_latest_missing_returns_none(db) -> None:
    assert patient_memory.latest_value(99, "收缩压") is None


def test_ensure_patient_creates_and_reuses(db) -> None:
    first = patient_memory.ensure_patient(7, "王女士")
    second = patient_memory.ensure_patient(7, "王女士")
    assert first.id == second.id == 7
    assert first.name == "王女士"


def test_create_patient_and_list(db) -> None:
    created = patient_memory.create_patient("赵先生")
    ids = [p.id for p in patient_memory.list_patients()]
    assert created.id in ids
    assert any(p.name == "赵先生" for p in patient_memory.list_patients())


def test_append_metric_auto_creates_patient_row(db) -> None:
    # P2-10：直接写指标时患者行自动创建，避免外键悬空。
    patient_memory.append_metric(42, "空腹血糖", 7.2, "mmol/L")
    patients = patient_memory.list_patients()
    assert any(p.id == 42 for p in patients)


def test_metric_snapshot_aggregates_latest_and_delta(db) -> None:
    """纵向记忆快照（P1-F）：最新值、单位与较前值变化一次聚合，无数据为空。"""
    assert patient_memory.metric_snapshot(1) == {}
    patient_memory.append_metric(1, "收缩压", 140.0, "mmHg")
    patient_memory.append_metric(1, "收缩压", 150.0, "mmHg")
    patient_memory.append_metric(1, "空腹血糖", 7.2, "mmol/L")
    snapshot = patient_memory.metric_snapshot(1)
    assert snapshot["收缩压"] == (150.0, "mmHg", 10.0)
    assert snapshot["空腹血糖"] == (7.2, "mmol/L", None)
