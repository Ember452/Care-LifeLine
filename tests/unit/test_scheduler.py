from care_lifeline.config import get_settings
from care_lifeline.proactive.scheduler import DistributedLock, get_latest_reminders, run_once


def test_distributed_lock_acquire_release(tmp_path) -> None:
    lock = DistributedLock(tmp_path / ".lock")
    assert lock.acquire() is True
    assert lock.acquire() is False  # 同主机不可重复获得
    lock.release()
    assert lock.acquire() is True
    lock.release()


def test_run_once_caches_reminders(tmp_path, monkeypatch) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/pro.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    from care_lifeline.db.engine import init_db, reset_state_for_testing

    reset_state_for_testing()
    init_db()
    from care_lifeline.db import session_store
    from care_lifeline.memory import patient_memory

    session_store.seed_demo_user()
    patient_memory.append_metric(1, "收缩压", 150.0)

    snapshot = run_once()
    assert 1 in snapshot
    assert snapshot[1]  # 150 > 140 触发提醒
    assert get_latest_reminders(1) == snapshot[1]
