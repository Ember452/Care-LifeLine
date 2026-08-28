"""质控第二层：LLM 语义评审（规则层无命中时才进入）。

评审 prompt 采用 rubric + few-shot + 结构化 JSON 输出（契约 §E），
替代改造前「请评估以下医疗回复的风险分数」这种裸 prompt。
"""

from __future__ import annotations

import json
import logging
import re

from care_lifeline.graph.state import QCResult
from care_lifeline.llm.prompts import QC_REVIEW_PROMPT, render
from care_lifeline.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)
_FALLBACK_RISK_SCORE = 0.5


class LLMReviewer:
    """对模型草稿做风险打分，超过阈值即转人工。"""

    def __init__(self, provider: LLMProvider | None = None, threshold: float = 0.75) -> None:
        self.provider = provider
        self.threshold = threshold

    def check(self, draft: str, ctx: dict | None = None) -> QCResult:
        """评审一条草稿。

        Args:
            draft: 待评审的模型草稿。
            ctx: 上下文，识别 ``risk_level``（``critical`` 时直接转人工）。

        Returns:
            含 ``status`` / ``risk_score`` / ``violations`` 的质控结果。
        """
        if self.provider is None:
            risk_level = (ctx or {}).get("risk_level", "routine")
            risk_score = 0.95 if risk_level == "critical" else 0.1
            violations: list[str] = []
        else:
            risk_score, violations = self._review_with_llm(draft)
        status = "hitl" if risk_score >= self.threshold else "passed"
        return QCResult(status=status, risk_score=risk_score, violations=violations)

    def _review_with_llm(self, draft: str) -> tuple[float, list[str]]:
        assert self.provider is not None
        prompt = render(QC_REVIEW_PROMPT, draft=draft)
        output = self.provider.complete(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": draft}]
        )
        parsed = _parse_review_json(output)
        if parsed is not None:
            return parsed
        try:
            return float(output.strip()), []
        except ValueError:
            logger.warning(
                "qc_review_unparsable_output", extra={"output_length": len(output or "")}
            )
            return _FALLBACK_RISK_SCORE, []


def _parse_review_json(raw: str) -> tuple[float, list[str]] | None:
    """解析评审输出里的 JSON；无法解析时返回 ``None`` 由调用方降级。"""
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    score = payload.get("risk_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    raw_violations = payload.get("violations", [])
    violations = (
        [item for item in raw_violations if isinstance(item, str)]
        if isinstance(raw_violations, list)
        else []
    )
    return float(score), violations
