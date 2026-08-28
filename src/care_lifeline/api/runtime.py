from __future__ import annotations

import math
import threading

# 进程内延迟采样（管理后台 p95 的真实数据源）。
# 请求热路径只追加采样，避免引入 DB 写入开销；进程重启后清空可接受。
_MAX_SAMPLES = 1000

_lock = threading.Lock()
_latencies_ms: list[float] = []


def record_latency_ms(ms: float) -> None:
    """记录一次请求端到端延迟（毫秒）。

    Args:
        ms: 实测耗时，须 >= 0。
    """
    with _lock:
        _latencies_ms.append(ms)
        if len(_latencies_ms) > _MAX_SAMPLES:
            del _latencies_ms[: len(_latencies_ms) - _MAX_SAMPLES]


def p95_latency_ms() -> float:
    """返回已采样延迟的 P95（毫秒）；无样本时返回 0.0。"""
    with _lock:
        if not _latencies_ms:
            return 0.0
        ordered = sorted(_latencies_ms)
        idx = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
        return round(ordered[idx], 2)
