from __future__ import annotations

from care_lifeline.graph.state import QCResult
from care_lifeline.llm.provider import LLMProvider


class LLMReviewer:
    def __init__(self, provider: LLMProvider | None = None, threshold: float = 0.75) -> None:
        self.provider = provider
        self.threshold = threshold

    def check(self, draft: str, ctx: dict | None = None) -> QCResult:
        if self.provider is None:
            risk_level = (ctx or {}).get("risk_level", "routine")
            risk_score = 0.95 if risk_level == "critical" else 0.1
        else:
            risk_score = self._score_with_llm(draft)
        status = "hitl" if risk_score >= self.threshold else "passed"
        return QCResult(status=status, risk_score=risk_score, violations=[])

    def _score_with_llm(self, draft: str) -> float:
        assert self.provider is not None
        prompt = f"请评估以下医疗回复的风险分数(0到1之间的小数):\n{draft}"
        output = self.provider.complete(messages=[{"role": "user", "content": prompt}])
        try:
            return float(output.strip())
        except ValueError:
            return 0.5
