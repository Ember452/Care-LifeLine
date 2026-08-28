from collections.abc import Iterator

from care_lifeline.llm.provider import ModelTier
from care_lifeline.safety.keywords import EMERGENCY_KEYWORDS, REPORT_KEYWORDS


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


class MockProvider:
    """Rule-driven provider that returns deterministic, realistic responses.

    Used when ``LLM_MODE=mock`` so the whole stack runs without external APIs.
    关键词与 :mod:`care_lifeline.safety.keywords` 共享，避免判定口径漂移。
    ``tier`` 在本实现中被忽略（mock 无模型分层）。
    """

    def _respond(self, text: str) -> str:
        if any(keyword in text for keyword in EMERGENCY_KEYWORDS):
            return (
                "您描述的症状（如胸痛、呼吸困难）属于急症信号，请立即前往最近的急诊科，"
                "或拨打急救电话，不要等待或自行服药。"
            )
        if any(keyword in text for keyword in REPORT_KEYWORDS):
            return (
                "根据您提供的化验单，以下指标需要关注：请结合参考范围判断偏高/偏低项。"
                "建议复诊时携带完整报告，由医生结合病史综合评估。（引用自临床检验指南）"
            )
        return (
            "我已记录您的症状。为便于分诊，请补充：症状持续时间、是否伴随发热、"
            "既往病史与正在服用的药物。"
        )

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> str:
        return self._respond(_last_user_text(messages))

    def stream(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> Iterator[str]:
        yield from self._respond(_last_user_text(messages)).split("，")
