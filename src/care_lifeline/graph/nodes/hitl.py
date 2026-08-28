from __future__ import annotations

from langgraph.types import interrupt

from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import LLMProvider

ESCALATION_DRAFT = "⚠️ 检测到高危症状，已为您转接人工医生，请保持冷静并尽快前往急诊或拨打急救电话。"
INTERRUPT_REASON = "检测到高危症状，需人工医生复核"
_INTERRUPT_KEY = "hitl_review"


def escalation_payload(state: AgentState) -> dict[str, object]:
    """构造 interrupt 载荷。

    只携带判定原因与风险等级，**不含用户输入原文**，避免 PHI 进入持久化检查点。
    """
    return {
        "node": "hitl",
        "reason": INTERRUPT_REASON,
        "risk_level": state.get("risk_level", "critical"),
    }


def draft_from_decision(decision: object) -> str:
    """把人工恢复时的决策转成本轮草稿。

    Args:
        decision: ``Command(resume=...)`` 传入的恢复载荷，期望为含
            ``corrected_text`` 的 dict；其余情况一律回落到标准转人工文案。

    Returns:
        人工修正后的文本，或标准转人工文案。
    """
    corrected = decision.get("corrected_text") if isinstance(decision, dict) else None
    if isinstance(corrected, str) and corrected.strip():
        return corrected.strip()
    return ESCALATION_DRAFT


def escalate_node(
    state: AgentState,
    provider: LLMProvider | None = None,
    *,
    interrupt_enabled: bool = False,
) -> dict[str, object]:
    """转人工节点（契约 §4.1）。

    Postgres 模式（有 checkpointer）用 ``langgraph.types.interrupt()`` 真暂停，
    由 ``POST /v1/hitl/resume`` 以 ``Command(resume=...)`` 恢复；无 checkpointer
    时降级为软 HITL（直接产出转人工文案），保证不阻塞。
    """
    if not interrupt_enabled:
        return {"draft": ESCALATION_DRAFT}
    decision = interrupt({_INTERRUPT_KEY: escalation_payload(state)})
    return {"draft": draft_from_decision(decision)}
