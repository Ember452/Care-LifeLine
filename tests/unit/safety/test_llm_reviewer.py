"""质控 LLM 评审单测：结构化 JSON 解析 + 降级路径。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from care_lifeline.llm.provider import ModelTier
from care_lifeline.safety.llm_reviewer import LLMReviewer


class _StubProvider:
    def __init__(self, output: str) -> None:
        self._output = output

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> str:
        assert messages[0]["role"] == "system"
        assert "评分细则" in messages[0]["content"]
        return self._output

    def stream(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> Iterator[str]:
        yield self._output


def test_reviewer_无provider且critical_转人工() -> None:
    result = LLMReviewer(provider=None).check("胸痛患者", {"risk_level": "critical"})

    assert result.status == "hitl"
    assert result.risk_score == 0.95


def test_reviewer_无provider且routine_放行() -> None:
    result = LLMReviewer(provider=None).check("建议休息", {"risk_level": "routine"})

    assert result.status == "passed"
    assert result.risk_score == 0.1


def test_reviewer_无provider且无ctx_按routine处理() -> None:
    assert LLMReviewer(provider=None).check("建议休息").status == "passed"


def test_reviewer_阈值下调_低分也转人工() -> None:
    result = LLMReviewer(provider=None, threshold=0.05).check("建议休息", {"risk_level": "routine"})

    assert result.status == "hitl"


def test_reviewer_JSON输出_解析出分数与违规项() -> None:
    raw = '{"risk_score": 0.9, "violations": ["确定性诊断"], "rationale": "给出诊断"}'

    result = LLMReviewer(provider=_StubProvider(raw)).check("您患有肺炎", {})

    assert result.risk_score == 0.9
    assert result.violations == ["确定性诊断"]
    assert result.status == "hitl"


def test_reviewer_JSON违规项非字符串_过滤为空列表() -> None:
    raw = '{"risk_score": 0.1, "violations": [1, "缺少引用"]}'

    result = LLMReviewer(provider=_StubProvider(raw)).check("建议休息", {})

    assert result.violations == ["缺少引用"]
    assert result.status == "passed"


def test_reviewer_JSON违规项非列表_回落为空列表() -> None:
    result = LLMReviewer(provider=_StubProvider('{"risk_score": 0.1}')).check("建议休息", {})

    assert result.status == "passed"
    assert result.violations == []


def test_reviewer_裸小数输出_兼容旧格式() -> None:
    result = LLMReviewer(provider=_StubProvider("0.2")).check("建议休息", {})

    assert result.risk_score == 0.2
    assert result.status == "passed"


@pytest.mark.parametrize(
    "raw",
    [
        "没有 JSON",
        "{坏掉的 JSON}",
        '{"risk_score": "高风险"}',
        '{"risk_score": true}',
    ],
)
def test_reviewer_输出无法解析_回落默认分并记录日志(
    raw: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="care_lifeline.safety.llm_reviewer"):
        result = LLMReviewer(provider=_StubProvider(raw), threshold=0.75).check("建议休息", {})

    assert result.risk_score == 0.5
    assert result.status == "passed"
    assert caplog.records[0].message == "qc_review_unparsable_output"
