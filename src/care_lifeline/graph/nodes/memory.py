"""患者纵向记忆节点（P1-F + §7.4 结构化上下文）。

把指标时序摘要与结构化纵向记忆（用药史/过敏史/随访计划）注入图状态
``memory_context``，供分诊提示词引用，实现"同一位患者越问越懂"。
跨会话仅保留结构化脱敏字段，不做自由文本长期留存（隐私边界）。
"""

from __future__ import annotations

from care_lifeline.graph.state import AgentState
from care_lifeline.memory.patient_memory import metric_snapshot, structured_summary


def memory_recall_node(state: AgentState) -> dict[str, str]:
    """调取患者纵向记忆（指标 + 用药/过敏/随访）并写入 ``memory_context``。

    未提供 ``patient_id`` 或该患者既无指标也无结构化记忆时返回空增量，
    不产出噪声记忆，也不影响无患者上下文的调用方（评测/匿名会话）。
    """
    patient_id = state.get("patient_id")
    if not patient_id:
        return {}
    snapshot = metric_snapshot(int(patient_id))
    parts: list[str] = []
    for name, (value, unit, delta) in snapshot.items():
        unit_text = f" {unit}" if unit else ""
        if delta is None:
            parts.append(f"{name}：最新 {value:g}{unit_text}")
            continue
        direction = "上升" if delta > 0 else ("下降" if delta < 0 else "持平")
        parts.append(f"{name}：最新 {value:g}{unit_text}（较前次 {delta:+g}，{direction}）")
    structured = structured_summary(int(patient_id))
    if structured:
        parts.append(structured)
    if not parts:
        return {}
    return {"memory_context": "；".join(parts)}
