from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

from care_lifeline.config import get_settings
from care_lifeline.memory import patient_memory
from care_lifeline.proactive.trigger import Reminder, evaluate

_LOCK_PATH = Path(os.getenv("CARE_TMP_DIR", "")) / ".care_proactive_lock"


class DistributedLock:
    """Best-effort file-based lock preventing two scheduler instances from
    double-running on the same host. Swap for Redis in multi-host deployments.
    """

    def __init__(self, path: Path = _LOCK_PATH) -> None:
        self._path = path

    def acquire(self) -> bool:
        try:
            fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        os.close(fd)
        return True

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
