from __future__ import annotations

from langchain_core.messages import HumanMessage

from care_lifeline.config import get_settings
from care_lifeline.graph.state import AgentState, QCResult
from care_lifeline.safety.llm_reviewer import LLMReviewer
from care_lifeline.safety.rules_engine import Severity, evaluate_all, load_ruleset


def qc_node(state: AgentState, provider) -> dict:
    """Double-layer QC: rules engine + LLM semantic review (M2-3)."""
    draft = state.get("draft") or ""
    if not draft:
        return {
            "qc_result": QCResult(
                status="refused", risk_score=0.9, violations=["无法生成安全回复"]
            ),
            "hitl_required": False,
        }

    user_text = ""
    for message in reversed(state.get("messages") or []):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            user_text = message.content
            break
    qc_text = f"{user_text}\n{draft}" if user_text else draft

    ctx = {"risk_level": state.get("risk_level", "routine")}
    violations = evaluate_all(load_ruleset(1), qc_text, ctx)
    messages = [v.message for v in violations]
    blocking = next((v for v in violations if v.severity is Severity.BLOCKING), None)
    if blocking is not None:
        is_emergency = blocking.code == "emergency"
        status = "hitl" if is_emergency else "refused"
        return {
            "qc_result": QCResult(status=status, risk_score=0.95, violations=messages),
            "hitl_required": is_emergency,
        }

    threshold = get_settings().qc_risk_threshold
    mode = get_settings().llm_mode
    reviewer = LLMReviewer(provider if mode == "real" else None, threshold)
    llm = reviewer.check(draft, ctx)
    return {"qc_result": llm, "hitl_required": llm.status == "hitl"}
