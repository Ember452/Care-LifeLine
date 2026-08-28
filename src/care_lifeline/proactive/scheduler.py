from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
import time
from pathlib import Path

from care_lifeline.config import get_settings
from care_lifeline.memory import patient_memory
from care_lifeline.proactive.trigger import Reminder, evaluate

# 锁文件默认落在系统临时目录：CWD 相对路径会在项目根残留锁文件，
# 且不同工作目录下无法互斥（根因见 test_run_once_caches_reminders 的修复）。
_LOCK_DIR = Path(os.getenv("CARE_TMP_DIR") or tempfile.gettempdir())
_LOCK_PATH = _LOCK_DIR / ".care_proactive_lock"
# 陈旧锁回收阈值：进程崩溃后残留的锁超过该时长即可被回收。
_LOCK_STALE_SECONDS = 300.0


class DistributedLock:
    """Best-effort file-based lock preventing two scheduler instances from
    double-running on the same host. Swap for Redis in multi-host deployments.
    """

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


_LATEST: dict[int, list[Reminder]] = {}
_TASK: asyncio.Task | None = None


def get_latest_reminders(patient_id: int) -> list[Reminder]:
    """Return the most recent proactive reminders produced by the scheduler."""
    return _LATEST.get(patient_id, [])


def run_once() -> dict[int, list[Reminder]]:
    """Scan every patient and cache reminders above clinical thresholds."""
    global _LATEST
    lock = DistributedLock()
    if not lock.acquire():
        return _LATEST
    try:
        snapshot: dict[int, list[Reminder]] = {}
        for patient_id in patient_memory.list_patient_ids():
            snapshot[patient_id] = evaluate(patient_id)
        _LATEST = snapshot
        return snapshot
    finally:
        lock.release()


async def _loop(interval: int) -> None:
    while True:
        with contextlib.suppress(Exception):
            run_once()
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
