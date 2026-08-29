from __future__ import annotations

import math
import threading

from care_lifeline.llm.provider import TokenUsage

# 进程内运行时指标（管理后台 /v1/admin/metrics 的真实数据源）。
# 请求热路径只追加采样，避免引入 DB 写入开销；进程重启后清空可接受。
_MAX_SAMPLES = 1000
_MAX_SESSIONS = 200

_lock = threading.Lock()
_latencies_ms: list[float] = []
_node_ms: dict[str, list[float]] = {}
_qc_counts: dict[str, int] = {}
_token_totals: dict[str, int] = {"input": 0, "output": 0}
_token_estimated_count = 0
_token_request_count = 0
# 每会话累计 token（有界：超出后淘汰最旧，防内存无界增长）。
_session_tokens: dict[str, TokenUsage] = {}


def reset_runtime_metrics() -> None:
    """清空全部运行时指标（测试隔离用）。"""
    global _token_estimated_count, _token_request_count
    with _lock:
        _latencies_ms.clear()
        _node_ms.clear()
        _qc_counts.clear()
        _token_totals["input"] = 0
        _token_totals["output"] = 0
        _token_estimated_count = 0
        _token_request_count = 0
        _session_tokens.clear()


def record_latency_ms(ms: float) -> None:
    """记录一次请求端到端延迟（毫秒）。

    Args:
        ms: 实测耗时，须 >= 0。
    """
    with _lock:
        _append_capped(_latencies_ms, ms)


def p95_latency_ms() -> float:
    """返回已采样端到端延迟的 P95（毫秒）；无样本时返回 0.0。"""
    with _lock:
        return _p95(_latencies_ms)


def record_node_ms(node: str, ms: float) -> None:
    """记录单个图节点的执行耗时（毫秒）。"""
    with _lock:
        _append_capped(_node_ms.setdefault(node, []), ms)


def node_latency_summary() -> dict[str, dict[str, float]]:
    """返回每个节点的 {count, p50_ms, p95_ms} 汇总；无样本时为空表。"""
    with _lock:
        return {
            node: {
                "count": len(samples),
                "p50_ms": _p50(samples),
                "p95_ms": _p95(samples),
            }
            for node, samples in sorted(_node_ms.items())
        }


def record_qc_status(status: str) -> None:
    """记录一次质控结论（passed/warning/hitl/refused）计数。"""
    with _lock:
        _qc_counts[status] = _qc_counts.get(status, 0) + 1


def qc_status_counts() -> dict[str, int]:
    """返回质控结论计数快照。"""
    with _lock:
        return dict(sorted(_qc_counts.items()))


def record_token_usage(session_id: str, usage: TokenUsage) -> None:
    """记录一次请求的 token 用量（全局累计 + 会话累计）。"""
    global _token_estimated_count, _token_request_count
    with _lock:
        _token_totals["input"] += usage.input_tokens
        _token_totals["output"] += usage.output_tokens
        _token_request_count += 1
        if usage.estimated:
            _token_estimated_count += 1
        merged_input = _session_tokens.get(session_id)
        if merged_input is not None:
            usage = TokenUsage(
                input_tokens=merged_input.input_tokens + usage.input_tokens,
                output_tokens=merged_input.output_tokens + usage.output_tokens,
                estimated=merged_input.estimated and usage.estimated,
            )
        if len(_session_tokens) >= _MAX_SESSIONS and session_id not in _session_tokens:
            # 有界淘汰：删最早插入的一条（dict 保序）。
            oldest = next(iter(_session_tokens))
            del _session_tokens[oldest]
        _session_tokens[session_id] = usage


def token_summary() -> dict[str, object]:
    """返回 token 用量汇总（全局累计 + 最近会话明细快照）。"""
    with _lock:
        return {
            "total_input_tokens": _token_totals["input"],
            "total_output_tokens": _token_totals["output"],
            "request_count": _token_request_count,
            "estimated_request_count": _token_estimated_count,
            "sessions": {
                session_id: {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "estimated": usage.estimated,
                }
                for session_id, usage in list(_session_tokens.items())[-20:]
            },
        }


def _append_capped(samples: list[float], value: float) -> None:
    samples.append(value)
    if len(samples) > _MAX_SAMPLES:
        del samples[: len(samples) - _MAX_SAMPLES]


def _p50(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[(len(ordered) - 1) // 2], 2)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[idx], 2)
