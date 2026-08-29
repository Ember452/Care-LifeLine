from __future__ import annotations

import json
from collections.abc import Iterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from care_lifeline.llm.provider import ModelTier, TokenUsage, ToolSpec, estimate_usage
from care_lifeline.safety.keywords import EMERGENCY_KEYWORDS, REPORT_KEYWORDS

# mock 工具调用轮的固定 tool_call id（确定性输出，便于测试断言）。
_MOCK_TOOL_CALL_ID = "call_mock_0"


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _last_user_text_lc(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


class MockProvider:
    """Rule-driven provider that returns deterministic, realistic responses.

    Used when ``LLM_MODE=mock`` so the whole stack runs without external APIs.
    关键词与 :mod:`care_lifeline.safety.keywords` 共享，避免判定口径漂移。
    ``tier`` 在本实现中被忽略（mock 无模型分层）。

    工具循环的确定性脚本：首轮命中 ``drug_interaction`` 即发起工具调用，
    工具结果回填后基于 JSON 结果生成最终回答——两轮走完真实 ReAct 通路。

    ``last_usage`` 恒为按字符估算的用量（``estimated=True``），保证可观测性
    管线在 mock 模式同样可回归，但不代表真实计量。
    """

    last_usage: TokenUsage | None = None

    def _track(self, input_text: str, output_text: str) -> str:
        self.last_usage = estimate_usage(input_text, output_text)
        return output_text

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
        text = _last_user_text(messages)
        return self._track(text, self._respond(text))

    def stream(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> Iterator[str]:
        output = self._respond(_last_user_text(messages))
        self._track(_last_user_text(messages), output)
        yield from output.split("，")

    def invoke_with_tools(
        self,
        *,
        messages: list[BaseMessage],
        tools: list[ToolSpec],
        temperature: float = 0.2,
        tier: ModelTier = "strong",
    ) -> AIMessage:
        user_text = _last_user_text_lc(messages)
        tool_names = {spec.name for spec in tools}
        has_tool_result = any(isinstance(message, ToolMessage) for message in messages)
        if has_tool_result:
            answer = self._answer_from_tool_result(messages)
            return AIMessage(content=self._track(user_text, answer))
        if "drug_interaction" in tool_names:
            self._track(user_text, "")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "drug_interaction",
                        "args": {"drugs": user_text},
                        "id": _MOCK_TOOL_CALL_ID,
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content=self._track(user_text, self._respond(user_text)))

    def _answer_from_tool_result(self, messages: list[BaseMessage]) -> str:
        """把回填的工具结果转成最终回答；解析失败降级为通用建议。"""
        tool_message = next(
            (m for m in reversed(messages) if isinstance(m, ToolMessage)), None
        )
        if tool_message is None:
            return self._respond(_last_user_text_lc(messages))
        try:
            payload = json.loads(str(tool_message.content))
        except json.JSONDecodeError:
            payload = {}
        if not payload.get("ok"):
            return (
                "药物相互作用查询暂时不可用，请咨询医师或药师后再调整用药。"
                "（引用自离线药物相互作用知识库）"
            )
        hits = payload.get("data", {}).get("interactions", [])
        if hits:
            pairs = "；".join(
                f"{hit.get('a')} + {hit.get('b')}（{hit.get('severity')}）：{hit.get('note')}"
                for hit in hits
            )
            return (
                f"查询到 {len(hits)} 项药物相互作用：{pairs}。"
                "建议咨询医师或药师，不要自行调整用药方案。（引用自离线药物相互作用知识库）"
            )
        return (
            "未查询到您提到的药物之间的相互作用记录。仍建议在医师或药师指导下用药，"
            "如出现不适请及时就医。（引用自离线药物相互作用知识库）"
        )
