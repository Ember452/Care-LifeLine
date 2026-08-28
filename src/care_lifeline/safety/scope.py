"""请求范围分类器（scope classifier）。

解决全量重构契约 §2.1 的根因：改造前系统没有任何机制判断「这是不是医疗问题」，
质控规则只在模型回复 draft 里找「开处方/开药/诊断结论」，而模型永远不会输出这些词，
导致非医疗与越权请求 100% 泄漏。

判定在**用户输入侧**完成，短路顺序（优先级从高到低）：
``UNSAFE`` → ``OUT_OF_SCOPE`` → ``RESTRICTED`` → ``IN_SCOPE``。

mock 模式只跑规则，保证零外部依赖、确定性可测；real 模式下规则未命中时
再用轻量模型做一次「是否医疗意图」的结构化兜底判定。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from care_lifeline.config import get_settings
from care_lifeline.llm.prompts import SCOPE_CLASSIFY_PROMPT, render
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.safety.keywords import (
    NON_MEDICAL_KEYWORDS,
    NON_MEDICAL_PATTERNS,
    PRESCRIPTION_CONTEXT_PATTERNS,
    RESTRICTED_PATTERNS,
    UNSAFE_KEYWORDS,
)

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


class ScopeVerdict(StrEnum):
    """请求范围判定结果。"""

    IN_SCOPE = "in_scope"  # 正常医疗咨询，继续走图
    OUT_OF_SCOPE = "out_of_scope"  # 非医疗问题 → 拒答
    RESTRICTED = "restricted"  # 越权医疗请求（开处方/下诊断/开证明）→ 拒答
    UNSAFE = "unsafe"  # 自杀/自伤/违法 → 拒答 + 强提示


@dataclass
class ScopeResult:
    """一次范围判定的完整结果。

    Attributes:
        verdict: 判定结论。
        reason: 人类可读原因，进审计与 SSE 事件。
        matched: 命中的规则或关键词；规则未命中（含兜底放行）时为 ``None``。
    """

    verdict: ScopeVerdict
    reason: str
    matched: str | None = None


def classify_scope(user_text: str, provider: LLMProvider | None = None) -> ScopeResult:
    """判定一条用户输入是否在本助手的服务范围内。

    Args:
        user_text: 用户原始输入（应已完成 PHI 脱敏）。
        provider: LLM 提供者；仅当处于 real 模式且规则未命中时用于意图兜底判定。

    Returns:
        :class:`ScopeResult`。永不抛异常：LLM 兜底失败时按规则结论放行。
    """
    unsafe_match = _match_keywords(user_text, UNSAFE_KEYWORDS)
    if unsafe_match is not None:
        return ScopeResult(
            ScopeVerdict.UNSAFE, f"命中高危安全词「{unsafe_match}」，不予协助", unsafe_match
        )

    non_medical_match = _match_non_medical(user_text)
    if non_medical_match is not None:
        return ScopeResult(
            ScopeVerdict.OUT_OF_SCOPE,
            f"非医疗健康咨询（命中「{non_medical_match}」），超出服务范围",
            non_medical_match,
        )

    if _llm_says_non_medical(user_text, provider):
        return ScopeResult(ScopeVerdict.OUT_OF_SCOPE, "模型判定为非医疗意图", "llm_classifier")

    restricted_match = _match_restricted(user_text)
    if restricted_match is not None:
        return ScopeResult(
            ScopeVerdict.RESTRICTED,
            f"越权医疗请求（命中「{restricted_match}」），需执业医师面诊",
            restricted_match,
        )

    return ScopeResult(ScopeVerdict.IN_SCOPE, "常规医疗咨询，进入分诊流程")


def _match_keywords(text: str, keywords: tuple[str, ...]) -> str | None:
    """返回 ``text`` 中首个命中的关键词，全部未命中返回 ``None``。"""
    return next((keyword for keyword in keywords if keyword in text), None)


def _match_patterns(text: str, patterns: tuple[str, ...]) -> str | None:
    """返回首个命中 ``text`` 的正则源码，全部未命中返回 ``None``。"""
    return next((pattern for pattern in patterns if re.search(pattern, text, re.IGNORECASE)), None)


def _match_non_medical(text: str) -> str | None:
    """非医疗意图判定：先关键词，再正则（覆盖「用 Python 实现」这类表述）。"""
    keyword = _match_keywords(text, NON_MEDICAL_KEYWORDS)
    if keyword is not None:
        return keyword
    return _match_patterns(text, NON_MEDICAL_PATTERNS)


def _match_restricted(text: str) -> str | None:
    """越权医疗请求判定。

    已开具/正在服用的语境（「医生给我开了降压药」）属于陈述而非索取，
    跳过开药类规则，避免把正常的用药咨询误判为越权。
    """
    if _match_patterns(text, PRESCRIPTION_CONTEXT_PATTERNS) is not None:
        return None
    return _match_patterns(text, RESTRICTED_PATTERNS)


def _llm_says_non_medical(text: str, provider: LLMProvider | None) -> bool:
    """real 模式下用轻量模型做一次意图兜底；mock 模式直接短路返回 ``False``。

    LLM 调用失败时记录结构化日志（不含用户输入原文，避免 PHI 入日志）并放行，
    由下游质控规则继续把关。
    """
    if provider is None or get_settings().llm_mode != "real":
        return False
    prompt = render(SCOPE_CLASSIFY_PROMPT, user_text=text)
    try:
        raw = provider.complete(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            tier="fast",
        )
    except Exception as exc:  # 外部调用失败：转领域语义（放行），不吞异常
        logger.warning(
            "scope_classifier_llm_unavailable",
            extra={"error_type": type(exc).__name__, "text_length": len(text)},
        )
        return False
    return _parse_is_medical(raw) is False


def _parse_is_medical(raw: str) -> bool | None:
    """从模型输出里解析 ``is_medical`` 字段；无法解析时返回 ``None`` 表示弃权。"""
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    value = payload.get("is_medical")
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None
