"""意图路由与请求范围判定节点。"""

from __future__ import annotations

import logging

from care_lifeline.config import get_settings
from care_lifeline.graph.state import AgentState, last_user_text
from care_lifeline.llm.prompts import INTENT_PROMPT, render
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.safety.keywords import (
    EMERGENCY_KEYWORDS,
    MEDICATION_KEYWORDS,
    REPORT_KEYWORDS,
)
from care_lifeline.safety.scope import ScopeResult, ScopeVerdict, classify_scope

logger = logging.getLogger(__name__)

_VALID_INTENTS = ("triage", "report", "medication")


def classify_intent(text: str, provider: LLMProvider | None = None) -> tuple[str, str]:
    """Return ``(risk_level, intent)`` from the latest user message.

    急症词命中必须走确定性规则（安全红线不做模型兜底）。其余意图在
    real 模式下交给轻量模型分类（修 P1-G：症状句含「血压」曾被关键词
    误判为报告解读），LLM 失败回落关键词结论；mock 模式保持纯关键词
    的确定性。
    """
    if any(keyword in text for keyword in EMERGENCY_KEYWORDS):
        return "critical", "emergency"
    if get_settings().llm_mode == "real" and provider is not None:
        intent = _llm_classify_intent(text, provider)
        if intent is not None:
            return "routine", intent
    keyword_intent = _keyword_intent(text)
    if keyword_intent is not None:
        return "routine", keyword_intent
    return "routine", "triage"


def _keyword_intent(text: str) -> str | None:
    """关键词意图分类；未命中返回 ``None``。"""
    if any(keyword in text for keyword in MEDICATION_KEYWORDS):
        return "medication"
    if any(keyword in text for keyword in REPORT_KEYWORDS):
        return "report"
    return None


def _llm_classify_intent(text: str, provider: LLMProvider) -> str | None:
    """real 模式意图兜底；返回合法意图名，失败/不可解析返回 ``None``。

    失败只记结构化日志（不落用户原文，避免 PHI 入日志），由调用方
    回落到关键词结论。
    """
    prompt = render(INTENT_PROMPT, user_text=text)
    try:
        raw = provider.complete(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            tier="fast",
        )
    except Exception as exc:  # 外部调用失败：转领域语义（回落关键词），不吞异常
        logger.warning(
            "intent_classifier_llm_unavailable",
            extra={"error_type": type(exc).__name__, "text_length": len(text)},
        )
        return None
    intent = raw.strip().strip("。. ").lower()
    return intent if intent in _VALID_INTENTS else None


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

    risk_level, intent = classify_intent(last_user_text(state["messages"]), provider)
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
