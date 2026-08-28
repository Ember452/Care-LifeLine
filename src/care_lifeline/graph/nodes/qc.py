from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage

from care_lifeline.config import get_settings
from care_lifeline.graph.state import AgentState, QCResult
from care_lifeline.safety.llm_reviewer import LLMReviewer
from care_lifeline.safety.rules_engine import (
    CURRENT_RULESET_VERSION,
    Severity,
    evaluate_all,
    load_ruleset,
)


def _last_user_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            return message.content
    return ""


def _build_ctx(state: AgentState) -> dict[str, object]:
    """组装规则上下文：风险等级 + 上游 scope 判定（契约 §2.4）。"""
    scope = state.get("scope_result")
    return {
        "risk_level": state.get("risk_level", "routine"),
        "scope_verdict": scope.verdict if scope is not None else None,
        "scope_reason": scope.reason if scope is not None else None,
    }


def qc_node(state: AgentState, provider) -> dict:
    """Double-layer QC: rules engine + LLM semantic review (M2-3).

    规则层产出三种结论：阻断（``hitl`` / ``refused``）、提醒（``warning``，
    交给 ``rewrite`` 节点重写）、无违规（进入 LLM 语义评审）。
    """
    draft = state.get("draft") or ""
    if not draft:
        return {
            "qc_result": QCResult(
                status="refused", risk_score=0.9, violations=["无法生成安全回复"]
            ),
            "hitl_required": False,
        }

    user_text = _last_user_text(state.get("messages") or [])
    qc_text = f"{user_text}\n{draft}" if user_text else draft

    ctx = _build_ctx(state)
    violations = evaluate_all(load_ruleset(CURRENT_RULESET_VERSION), qc_text, ctx)
    messages = [v.message for v in violations]
    blocking = next((v for v in violations if v.severity is Severity.BLOCKING), None)
    if blocking is not None:
        is_emergency = blocking.code == "emergency"
        return {
            "qc_result": QCResult(
                status="hitl" if is_emergency else "refused",
                risk_score=0.95,
                violations=messages,
            ),
            "hitl_required": is_emergency,
        }
    if violations:
        return {
            "qc_result": QCResult(status="warning", risk_score=0.5, violations=messages),
            "hitl_required": False,
        }

    threshold = get_settings().qc_risk_threshold
    mode = get_settings().llm_mode
    reviewer = LLMReviewer(provider if mode == "real" else None, threshold)
    llm = reviewer.check(draft, ctx)
    return {"qc_result": llm, "hitl_required": llm.status == "hitl"}
