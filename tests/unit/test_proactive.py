from __future__ import annotations

import pytest

from care_lifeline.config import get_settings
from care_lifeline.db.engine import init_db, reset_state_for_testing
from care_lifeline.memory import patient_memory
from care_lifeline.proactive import trigger


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/pro.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    yield
    reset_state_for_testing()


def test_evaluate_flags_high_blood_pressure(db) -> None:
    patient_memory.append_metric(1, "收缩压", 150.0)
    reminders = trigger.evaluate(1)
    assert any(r.metric == "收缩压" for r in reminders)


def test_evaluate_no_reminder_when_normal(db) -> None:
    patient_memory.append_metric(2, "收缩压", 120.0)
    assert trigger.evaluate(2) == []
