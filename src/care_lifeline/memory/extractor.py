"""记忆变更提取器：从对话中抽取候选记忆提议（写入必须经人工确认）。

双实现与项目 mock/real 哲学同构：
- mock 模式：确定性正则（「开始服用X」「停用X」「对X过敏」），零外部
  依赖，演示与 CI 可回归；
- real 模式：LLM 按 rubric 抽取 JSON，失败回落正则。

提取器只产出**提议**（excerpt 附对话原句依据），绝不直接写正式记忆表。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from care_lifeline.config import get_settings
from care_lifeline.llm.prompts import MEMORY_EXTRACT_PROMPT, render
from care_lifeline.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

ProposalKind = Literal["medication", "allergy", "followup"]

# 中文姓名/药名长度的保守边界；贪婪捕获后剥离句末语气词、按连词拆分。
_DRUG = r"([\u4e00-\u9fa5A-Za-z0-9]{2,12})"
_PARTICLES = "了呢吧啊"
_CONJUNCTIONS = "和与跟同及"

_ADD_RE = re.compile(rf"(?:开始服用|开始吃|正在服用|长期服用|在吃|服用了){_DRUG}")
_STOP_AFTER_RE = re.compile(rf"(?:停用|停掉|不再吃|停吃了){_DRUG}")
_STOP_BEFORE_RE = re.compile(rf"{_DRUG}(?:停用|停掉了|停了)")
_ALLERGY_RE = re.compile(r"对([\u4e00-\u9fa5A-Za-z0-9]{1,12})过敏")
_SENTENCE_SPLIT = re.compile(r"[。！？！\n]")


def _split_conjunctions(name: str) -> list[str]:
    """「布洛芬和阿司匹林」拆成多个药名候选。"""
    return [part for part in re.split(f"[{_CONJUNCTIONS}]", name) if len(part) >= 2]


class ProposalDraft(BaseModel):
    """一条候选记忆变更（未落库，等待人工确认）。"""

    kind: ProposalKind
    action: Literal["add", "stop"] = "add"
    payload: dict[str, Any] = Field(default_factory=dict)
    excerpt: str = ""

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        name = _payload_name(self.payload)
        return (self.kind, self.action, name)


def _payload_name(payload: dict[str, Any]) -> str:
    return str(payload.get("name") or payload.get("allergen") or payload.get("plan") or "")


def _excerpt_of(text: str, start: int, end: int) -> str:
    """取匹配所在的原句（对话原句是提议的依据，进确认界面展示）。"""
    for sentence in _SENTENCE_SPLIT.split(text):
        pos = text.find(sentence)
        if sentence.strip() and pos <= start <= pos + len(sentence) + 40:
            return sentence.strip()[:200]
    return text[max(0, start - 20) : end + 20]


def extract_proposals_regex(text: str) -> list[ProposalDraft]:
    """确定性正则抽取（mock 模式 / LLM 失败回落）。"""
    drafts: list[ProposalDraft] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(draft: ProposalDraft) -> None:
        key = draft.dedupe_key
        if key not in seen and key[-1]:
            seen.add(key)
            drafts.append(draft)

    for match in _ADD_RE.finditer(text):
        excerpt = _excerpt_of(text, match.start(), match.end())
        for name in _split_conjunctions(match.group(1).strip(_PARTICLES)):
            _add(
                ProposalDraft(
                    kind="medication",
                    action="add",
                    payload={"name": name},
                    excerpt=excerpt,
                )
            )
    for match in list(_STOP_AFTER_RE.finditer(text)) + list(_STOP_BEFORE_RE.finditer(text)):
        excerpt = _excerpt_of(text, match.start(), match.end())
        # 「我把阿司匹林停用了」的贪婪捕获会带上主语，剥离前缀
        name_part = match.group(1).strip(_PARTICLES).lstrip("我把")
        for name in _split_conjunctions(name_part):
            _add(
                ProposalDraft(
                    kind="medication",
                    action="stop",
                    payload={"name": name},
                    excerpt=excerpt,
                )
            )
    for match in _ALLERGY_RE.finditer(text):
        _add(
            ProposalDraft(
                kind="allergy",
                action="add",
                payload={"allergen": match.group(1).strip(_PARTICLES)},
                excerpt=_excerpt_of(text, match.start(), match.end()),
            )
        )
    return drafts


def _draft_from_llm_item(item: Any) -> ProposalDraft | None:
    """校验 LLM 输出的单条提议；缺关键字段/非法枚举返回 ``None``。"""
    if not isinstance(item, dict):
        return None
    kind = item.get("kind")
    if kind not in ("medication", "allergy", "followup"):
        return None
    action = item.get("action", "add")
    if action not in ("add", "stop"):
        return None
    payload: dict[str, Any] = {}
    if kind == "medication":
        name = str(item.get("name") or "").strip()
        if not name:
            return None
        payload["name"] = name[:32]
    elif kind == "allergy":
        allergen = str(item.get("allergen") or item.get("name") or "").strip()
        if not allergen:
            return None
        payload["allergen"] = allergen[:32]
    else:
        plan = str(item.get("plan") or item.get("name") or "").strip()
        if not plan:
            return None
        payload["plan"] = plan[:120]
    excerpt = str(item.get("excerpt") or "")[:200]
    return ProposalDraft(kind=kind, action=action, payload=payload, excerpt=excerpt)


def extract_proposals_llm(text: str, provider: LLMProvider) -> list[ProposalDraft] | None:
    """LLM 抽取；输出不可解析返回 ``None``（调用方回落正则）。"""
    prompt = render(MEMORY_EXTRACT_PROMPT, dialogue=text)
    output = provider.complete(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        tier="fast",
    )
    match = re.search(r"\[.*\]", output, re.DOTALL)
    if match is None:
        logger.warning("memory_extract_unparsable", extra={"output_length": len(output)})
        return None
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("memory_extract_bad_json", extra={"output_length": len(output)})
        return None
    drafts: list[ProposalDraft] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items if isinstance(items, list) else []:
        draft = _draft_from_llm_item(item)
        if draft is not None and draft.dedupe_key not in seen:
            seen.add(draft.dedupe_key)
            drafts.append(draft)
    return drafts


def extract_proposals(text: str, provider: LLMProvider | None = None) -> list[ProposalDraft]:
    """入口：real 模式优先 LLM 语义抽取（失败回落正则），mock 走正则。"""
    if not text.strip():
        return []
    settings = get_settings()
    if settings.llm_mode == "real" and provider is not None:
        try:
            drafts = extract_proposals_llm(text, provider)
            if drafts is not None:
                return drafts
        except Exception as exc:
            logger.warning(
                "memory_extract_llm_failed", extra={"error_type": type(exc).__name__}
            )
    return extract_proposals_regex(text)
