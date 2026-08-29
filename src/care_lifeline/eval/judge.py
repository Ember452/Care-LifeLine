"""有据率（groundedness）裁判：回复中的事实断言是否被引用支持（设计文档 §9.1）。

mock 模式用确定性代理（引用存在性），real 模式用 LLM-as-judge 按 rubric
逐断言核对；两者同一接口，评测套件按 provider 类型选择。
"""

from __future__ import annotations

import json
import logging
import re

from care_lifeline.graph.state import Citation
from care_lifeline.llm.prompts import GROUNDEDNESS_PROMPT, render
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.tools.report_interpreter import citation_has_real_source

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)


class MockGroundednessJudge:
    """确定性裁判：以「引用真实存在」为有据代理，供 CI/离线回归。

    这与 ``faithfulness``（引用存在率）口径一致是有意为之——mock 模式下
    没有可用的语义裁判，只保证管线回归；语义级有据率由 LLM 裁判提供。
    """

    def judge(self, draft: str, citations: list[Citation]) -> float | None:
        if not draft or not citations:
            return None
        return 1.0 if any(citation_has_real_source(c) for c in citations) else 0.0


class LLMGroundednessJudge:
    """LLM-as-judge：逐断言核对草稿与引用，输出 0-1 支持比例。

    解析失败/调用失败返回 ``None``（该用例不计入指标，而非记 0 分），
    避免「裁判故障」伪装成「回复无据」压低指标。
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def judge(self, draft: str, citations: list[Citation]) -> float | None:
        if not draft or not citations:
            return None
        rendered = "\n".join(f"[{c.index}] {c.source}：{c.snippet}" for c in citations)
        prompt = render(GROUNDEDNESS_PROMPT, draft=draft, citations=rendered)
        output = self._provider.complete(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": draft},
            ]
        )
        return self._parse(output)

    def _parse(self, raw: str) -> float | None:
        match = _JSON_OBJECT_RE.search(raw)
        if match is None:
            logger.warning("groundedness_unparsable_output", extra={"output_length": len(raw)})
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("groundedness_unparsable_json", extra={"output_length": len(raw)})
            return None
        ratio = payload.get("supported_ratio")
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
            logger.warning("groundedness_invalid_ratio", extra={"value_type": type(ratio).__name__})
            return None
        return min(1.0, max(0.0, float(ratio)))
