from care_lifeline.graph.state import AgentState, last_user_text
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.safety.keywords import (
    EMERGENCY_KEYWORDS,
    MEDICATION_KEYWORDS,
    REPORT_KEYWORDS,
)
from care_lifeline.safety.scope import ScopeResult, ScopeVerdict, classify_scope


def classify_intent(text: str) -> tuple[str, str]:
    """Return ``(risk_level, intent)`` from the latest user message."""
    if any(keyword in text for keyword in EMERGENCY_KEYWORDS):
        return "critical", "emergency"
    if any(keyword in text for keyword in MEDICATION_KEYWORDS):
        return "routine", "medication"
    if any(keyword in text for keyword in REPORT_KEYWORDS):
        return "routine", "report"
    return "routine", "triage"


def scope_check_node(state: AgentState, provider: LLMProvider | None = None) -> dict:
    """图的第一步：判定请求是否属于本助手的服务范围（契约 §2.2）。

    Args:
        state: 当前图状态。
        provider: LLM 提供者，仅 real 模式下用于意图兜底判定。

    Returns:
        仅含 ``scope_result`` 的增量更新。
    """
    return {"scope_result": classify_scope(last_user_text(state["messages"]), provider)}


def router_node(state: AgentState, provider: LLMProvider | None = None) -> dict:
    """按 scope 判定结果与关键词做意图分发。

    非 ``IN_SCOPE`` 一律置 ``intent="refuse"``，交由 ``refuse`` 节点产出拒答文案。
    """
    scope = _resolve_scope(state, provider)
    if scope.verdict is not ScopeVerdict.IN_SCOPE:
        return {
            "intent": "refuse",
            "risk_level": "critical" if scope.verdict is ScopeVerdict.UNSAFE else "routine",
            "scope_result": scope,
            "hitl_required": False,
        }

    risk_level, intent = classify_intent(last_user_text(state["messages"]))
    return {
        "intent": intent,
        "risk_level": risk_level,
        "scope_result": scope,
        "hitl_required": risk_level == "critical",
    }


def _resolve_scope(state: AgentState, provider: LLMProvider | None) -> ScopeResult:
    """复用 ``scope_check`` 节点的判定结果；缺失时（直接调用本节点）现算。"""
    cached = state.get("scope_result")
    if cached is not None:
        return cached
    return classify_scope(last_user_text(state["messages"]), provider)
