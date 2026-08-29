"""ReAct 工具智能体（graph/nodes/tool_agent.py）的行为测试。"""

import asyncio
import json
from typing import Any, ClassVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from care_lifeline.graph.nodes.tool_agent import ToolAgentConfig, run_tool_agent
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.llm.provider import ModelTier, ToolSpec


def _state(text: str) -> AgentState:
    return {  # type: ignore[typeddict-item]
        "messages": [HumanMessage(text)],
        "patient_id": None,
        "intent": "medication",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
    }


_DDI_SPEC = ToolSpec(
    name="drug_interaction", description="查相互作用", parameters={"type": "object"}
)


class _ScriptedProvider:
    """按脚本逐轮返回 AIMessage 的桩 provider，用于覆盖循环分支。"""

    def __init__(self, script: list[AIMessage]) -> None:
        self._script = script
        self.rounds = 0

    def complete(self, **kwargs: Any) -> str:
        raise NotImplementedError

    def stream(self, **kwargs: Any) -> Any:
        yield ""

    def invoke_with_tools(
        self,
        *,
        messages: list[BaseMessage],
        tools: list[ToolSpec],
        temperature: float = 0.2,
        tier: ModelTier = "strong",
    ) -> AIMessage:
        message = self._script[min(self.rounds, len(self._script) - 1)]
        self.rounds += 1
        return message


def test_run_tool_agent_mock_records_real_trace() -> None:
    outcome = asyncio.run(
        run_tool_agent(
            _state("华法林 阿司匹林 一起吃"),
            MockProvider(),
            ToolAgentConfig(system_prompt="测试约束", tool_names=("drug_interaction",)),
        )
    )
    assert len(outcome.traces) == 1
    trace = outcome.traces[0]
    assert trace.tool == "drug_interaction"
    assert trace.ok is True
    assert trace.error is None
    assert trace.latency_ms >= 0.0
    assert "interactions" in trace.summary
    assert "相互作用" in outcome.draft


def test_run_tool_agent_unregistered_tool_marks_error_and_recovers() -> None:
    first = AIMessage(
        content="",
        tool_calls=[{"name": "no_such_tool", "args": {}, "id": "c1", "type": "tool_call"}],
    )
    second = AIMessage(content="已改为直接回答")
    provider = _ScriptedProvider([first, second])
    outcome = asyncio.run(
        run_tool_agent(
            _state("任意输入"),
            provider,  # type: ignore[arg-type]
            ToolAgentConfig(system_prompt="测试约束", tool_names=("drug_interaction",)),
        )
    )
    assert outcome.traces[0].ok is False
    assert outcome.traces[0].error == "未注册的工具"
    assert outcome.draft == "已改为直接回答"
    assert provider.rounds == 2


def test_run_tool_agent_rounds_exhausted_falls_back() -> None:
    loop_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "drug_interaction",
                "args": {"drugs": ["华法林"]},
                "id": "c1",
                "type": "tool_call",
            }
        ],
    )
    provider = _ScriptedProvider([loop_call])
    outcome = asyncio.run(
        run_tool_agent(
            _state("任意输入"),
            provider,  # type: ignore[arg-type]
            ToolAgentConfig(
                system_prompt="测试约束", tool_names=("drug_interaction",), max_rounds=2
            ),
        )
    )
    assert len(outcome.traces) == 2
    assert outcome.traces[0].ok is True
    assert "暂时未能完成" in outcome.draft


def test_run_tool_agent_tool_failure_returns_error_result_to_model() -> None:
    """工具执行抛异常时回填错误结果，模型可继续作答而不是整轮失败。"""
    provider = _ScriptedProvider(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "drug_interaction",
                        "args": {"drugs": ["华法林"]},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="查询失败已说明"),
        ]
    )

    class _BrokenTool:
        name = "drug_interaction"
        description = "必失败"
        parameters: ClassVar[dict[str, Any]] = {"type": "object"}

        async def run(self, **kwargs: Any) -> Any:
            raise RuntimeError("下游超时")

    from care_lifeline.tools import registry

    original_tools = list(registry.ALL_TOOLS)
    registry.ALL_TOOLS = [_BrokenTool()]  # type: ignore[list-item]
    try:
        outcome = asyncio.run(
            run_tool_agent(
                _state("任意输入"),
                provider,  # type: ignore[arg-type]
                ToolAgentConfig(system_prompt="测试约束", tool_names=("drug_interaction",)),
            )
        )
    finally:
        registry.ALL_TOOLS = original_tools

    assert outcome.traces[0].ok is False
    assert "下游超时" in str(outcome.traces[0].error)
    assert outcome.draft == "查询失败已说明"


def test_run_tool_agent_tool_message_content_is_json() -> None:
    """回填内容必须是合法 JSON 字符串（mock 依赖此约定解析）。"""
    captured: list[BaseMessage] = []

    class _CaptureProvider(MockProvider):
        def invoke_with_tools(
            self,
            *,
            messages: list[BaseMessage],
            tools: list[ToolSpec],
            temperature: float = 0.2,
            tier: ModelTier = "strong",
        ) -> AIMessage:
            captured.extend(messages)
            return super().invoke_with_tools(
                messages=messages, tools=tools, temperature=temperature, tier=tier
            )

    asyncio.run(
        run_tool_agent(
            _state("华法林 阿司匹林"),
            _CaptureProvider(),
            ToolAgentConfig(system_prompt="测试约束", tool_names=("drug_interaction",)),
        )
    )
    tool_messages = [m for m in captured if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call_mock_0"
    payload = json.loads(str(tool_messages[0].content))
    assert payload["ok"] is True
    assert payload["data"]["interactions"][0]["severity"] == "major"
