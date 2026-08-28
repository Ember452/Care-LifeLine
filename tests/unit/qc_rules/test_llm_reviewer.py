from __future__ import annotations

from care_lifeline.llm.provider import LLMProvider
from care_lifeline.safety.llm_reviewer import LLMReviewer


class _FakeProvider(LLMProvider):
    def __init__(self, score: str) -> None:
        self._score = score

    def complete(self, *, messages, temperature: float = 0.2) -> str:
        return self._score

    def stream(self, *, messages, temperature: float = 0.2):
        yield self._score


def test_reviewer_mock_critical_returns_hitl() -> None:
    result = LLMReviewer(provider=None).check("胸痛患者", {"risk_level": "critical"})
    assert result.status == "hitl"
    assert result.risk_score == 0.95


def test_reviewer_mock_routine_passes() -> None:
    result = LLMReviewer(provider=None).check("建议休息", {"risk_level": "routine"})
    assert result.status == "passed"
    assert result.risk_score == 0.1


def test_reviewer_threshold_lowers_gate() -> None:
    result = LLMReviewer(provider=None, threshold=0.5).check("建议休息", {"risk_level": "routine"})
    assert result.status == "passed"
    assert result.risk_score < 0.5


def test_reviewer_real_high_score_hitl() -> None:
    result = LLMReviewer(provider=_FakeProvider("0.9")).check("建议用药", {})
    assert result.status == "hitl"
    assert result.risk_score == 0.9


def test_reviewer_real_low_score_passed() -> None:
    result = LLMReviewer(provider=_FakeProvider("0.2")).check("建议休息", {})
    assert result.status == "passed"
    assert result.risk_score == 0.2
