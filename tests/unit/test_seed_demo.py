from __future__ import annotations

from datetime import datetime

import pytest

from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import init_db, reset_state_for_testing
from care_lifeline.memory import patient_memory


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/seed.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    yield
    reset_state_for_testing()


def test_seed_creates_users_and_patients_and_metrics(db) -> None:
    from care_lifeline.db import seed_demo

    seed_demo.seed()
    # 三个角色用户
    assert session_store.verify_user("admin", "admin123") is not None
    assert session_store.verify_user("doctor", "doctor123") is not None
    assert session_store.verify_user("demo", "demo123") is not None
    # 患者 1 有纵向指标（慢病图表直接有数据）
    trend = patient_memory.get_trend(1, "收缩压")
    assert len(trend) >= 2
    values = [m.value for m in trend]
    assert all(v > 130 for v in values)
    assert isinstance(trend[0].measured_at, datetime)
