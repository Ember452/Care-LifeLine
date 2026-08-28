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
