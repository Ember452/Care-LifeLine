from __future__ import annotations

import time

from care_lifeline.config import get_settings
from care_lifeline.proactive.scheduler import DistributedLock, get_latest_reminders, run_once


def test_distributed_lock_acquire_release(tmp_path) -> None:
    lock = DistributedLock(tmp_path / ".lock")
    assert lock.acquire() is True
    assert lock.acquire() is False  # 同主机不可重复获得
    lock.release()
    assert lock.acquire() is True
    lock.release()


def test_lock_acquire_creates_parent_dir(tmp_path) -> None:
    lock = DistributedLock(tmp_path / "nested" / "dir" / ".lock")
    assert lock.acquire() is True
    assert lock._path.is_file()
    lock.release()


def test_stale_lock_is_reclaimed(tmp_path) -> None:
    lock = DistributedLock(tmp_path / ".lock", stale_after_seconds=0.01)
    assert lock.acquire() is True
    assert lock.acquire() is False  # 未陈旧前不可重入
    time.sleep(0.02)
    assert lock.acquire() is True  # 陈旧锁被回收
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

    # P2-F：提醒落库，重启（内存缓存清空）后仍能从库中读回。
    from care_lifeline.proactive import scheduler as scheduler_mod

    scheduler_mod._LATEST = {}
    restored = get_latest_reminders(1)
    assert len(restored) == 1
    assert restored[0].metric == "收缩压"
    assert restored[0].severity == "warning"

    # replace 语义：指标回落后新一轮扫描覆盖旧提醒。
    patient_memory.append_metric(1, "收缩压", 120.0)
    assert run_once()[1] == []
    assert get_latest_reminders(1) == []


def test_default_lock_path_is_absolute_not_cwd() -> None:
    import care_lifeline.proactive.scheduler as scheduler_mod

    lock = scheduler_mod.DistributedLock()
    assert lock._path.is_absolute()
    assert str(lock._path) != ".care_proactive_lock"


def test_make_lock_falls_back_to_file_when_redis_unavailable(monkeypatch) -> None:
    """选 redis 但锁初始化失败（如未装 redis 包/连不上配置错误）：回落文件锁并告警。"""
    from care_lifeline.config import get_settings
    from care_lifeline.proactive import scheduler as scheduler_mod
    from care_lifeline.proactive.scheduler import FileLock

    monkeypatch.setenv("CARE_PROACTIVE_LOCK_BACKEND", "redis")
    get_settings.cache_clear()

    def _boom(self, url, key="care:proactive_lock"):
        raise RuntimeError("redis unavailable")

    original = scheduler_mod.RedisLock
    scheduler_mod.RedisLock = _boom  # type: ignore[assignment]
    try:
        lock = scheduler_mod.make_lock()
        assert isinstance(lock, FileLock)
    finally:
        scheduler_mod.RedisLock = original
        get_settings.cache_clear()
