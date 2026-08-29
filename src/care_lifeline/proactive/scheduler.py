from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Protocol

from care_lifeline.config import get_settings
from care_lifeline.memory import patient_memory
from care_lifeline.proactive.trigger import Reminder, evaluate

logger = logging.getLogger(__name__)

# 锁文件默认落在系统临时目录：CWD 相对路径会在项目根残留锁文件，
# 且不同工作目录下无法互斥（根因见 test_run_once_caches_reminders 的修复）。
_LOCK_DIR = Path(os.getenv("CARE_TMP_DIR") or tempfile.gettempdir())
_LOCK_PATH = _LOCK_DIR / ".care_proactive_lock"
# 陈旧锁回收阈值：进程崩溃后残留的锁超过该时长即可被回收。
_LOCK_STALE_SECONDS = 300.0
# Redis 锁 TTL：与文件锁陈旧阈值同口径，持有者崩溃后锁自动过期。
_REDIS_TTL_SECONDS = 300


class SchedulerLock(Protocol):
    """调度互斥锁协议：同一时刻只允许一个实例执行扫描。"""

    def acquire(self) -> bool: ...

    def release(self) -> None: ...


class FileLock:
    """Best-effort file-based lock for single-host deployments."""

    def __init__(
        self, path: Path = _LOCK_PATH, stale_after_seconds: float = _LOCK_STALE_SECONDS
    ) -> None:
        self._path = path
        self._stale_after = stale_after_seconds

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not self._is_stale():
                return False
            # 陈旧锁回收后重试一次（进程崩溃遗留场景）。
            with contextlib.suppress(FileNotFoundError):
                self._path.unlink()
            return self.acquire()
        try:
            os.write(fd, str(time.time()).encode("utf-8"))
        finally:
            os.close(fd)
        return True

    def _is_stale(self) -> bool:
        try:
            return time.time() - self._path.stat().st_mtime > self._stale_after
        except FileNotFoundError:
            return False

    def release(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()


# 兼容别名：改造前 DistributedLock 即文件锁实现，既有调用方/测试无需改动。
DistributedLock = FileLock


class RedisLock:
    """Redis 分布式锁（SET NX EX + token 校验释放），供多主机部署。

    ``redis`` 包为可选依赖；构造时惰性导入，未安装抛 RuntimeError 由
    :func:`make_lock` 回落文件锁并告警。
    """

    def __init__(self, url: str, key: str = "care:proactive_lock") -> None:
        import redis  # type: ignore[import-not-found]  # 可选依赖：未安装时抛 ImportError

        self._key = key
        self._token = uuid.uuid4().hex
        self._client = redis.Redis.from_url(url)

    def acquire(self) -> bool:
        return bool(self._client.set(self._key, self._token, nx=True, ex=_REDIS_TTL_SECONDS))

    def release(self) -> None:
        # token 校验：只释放自己持有的锁，避免误删他实例的新锁。
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        self._client.eval(script, 1, self._key, self._token)


def make_lock() -> SchedulerLock:
    """按配置选择锁实现；Redis 不可用时回落文件锁并记警告（不阻塞调度）。"""
    settings = get_settings()
    if settings.proactive_lock_backend == "redis":
        try:
            return RedisLock(settings.redis_url)
        except Exception as exc:
            logger.warning(
                "proactive_redis_lock_unavailable",
                extra={"error_type": type(exc).__name__},
            )
    return FileLock()


_LATEST: dict[int, list[Reminder]] = {}
_TASK: asyncio.Task | None = None


def get_latest_reminders(patient_id: int) -> list[Reminder]:
    """Return the most recent proactive reminders produced by the scheduler.

    P2-F：优先读落库结果（重启/多实例一致）；库中无记录时回落进程内缓存。
    """
    from care_lifeline.db import session_store

    stored = session_store.list_reminders(patient_id)
    if stored:
        return [Reminder(patient_id=patient_id, **item) for item in stored]
    return _LATEST.get(patient_id, [])


def run_once() -> dict[int, list[Reminder]]:
    """Scan every patient and persist reminders above clinical thresholds."""
    global _LATEST
    lock = make_lock()
    if not lock.acquire():
        return _LATEST
    try:
        snapshot: dict[int, list[Reminder]] = {}
        for patient_id in patient_memory.list_patient_ids():
            snapshot[patient_id] = evaluate(patient_id)
        _LATEST = snapshot
        # P2-F：落库 replace，重启与多实例不再依赖进程内存。
        from care_lifeline.db import session_store

        for patient_id, reminders in snapshot.items():
            session_store.replace_reminders(patient_id, [r.model_dump() for r in reminders])
        return snapshot
    finally:
        lock.release()


async def _loop(interval: int) -> None:
    while True:
        with contextlib.suppress(Exception):
            # P2-F：同步 SQLAlchemy 扫描放线程池，不再阻塞事件循环。
            await asyncio.to_thread(run_once)
        await asyncio.sleep(interval)


def start_scheduler() -> None:
    """Start the background proactive loop (idempotent). No-op without patients."""
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    interval = get_settings().proactive_interval_seconds
    _TASK = asyncio.create_task(_loop(interval))


def stop_scheduler() -> None:
    global _TASK
    if _TASK is not None:
        _TASK.cancel()
        _TASK = None
