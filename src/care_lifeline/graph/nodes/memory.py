"""患者纵向记忆节点（P1-F）。

把 ``patients`` / ``patient_metrics`` 里的纵向指标摘要注入图状态
``memory_context``，供分诊提示词引用，实现"同一位患者越问越懂"。
"""

from __future__ import annotations

from care_lifeline.graph.state import AgentState
from care_lifeline.memory.patient_memory import metric_snapshot


def memory_recall_node(state: AgentState) -> dict[str, str]:
    """调取患者纵向指标摘要并写入 ``memory_context``。

    未提供 ``patient_id`` 或该患者尚无指标数据时返回空增量，
    不产出噪声记忆，也不影响无患者上下文的调用方（评测/匿名会话）。
    """
    patient_id = state.get("patient_id")
    if not patient_id:
        return {}
    snapshot = metric_snapshot(int(patient_id))
    if not snapshot:
        return {}
    parts: list[str] = []
    for name, (value, unit, delta) in snapshot.items():
        unit_text = f" {unit}" if unit else ""
        if delta is None:
            parts.append(f"{name}：最新 {value:g}{unit_text}")
            continue
        direction = "上升" if delta > 0 else ("下降" if delta < 0 else "持平")
        parts.append(f"{name}：最新 {value:g}{unit_text}（较前次 {delta:+g}，{direction}）")
    return {"memory_context": "；".join(parts)}
