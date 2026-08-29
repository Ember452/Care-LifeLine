"""ReAct 工具智能体：LLM 原生 tool-calling + 工具结果回填循环（契约 §5）。

与「单 prompt 节点」的区别：模型自主决定是否调用工具、调用哪个工具；
工具结果以 ``ToolMessage`` 回填后继续推理，直至产出最终回答或达到轮数上限。
每轮真实调用以 :class:`ToolTrace` 记录，驱动 SSE ``tool_call`` 事件与审计。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import ToolCall

from care_lifeline.graph.state import AgentState, ToolTrace
from care_lifeline.llm.provider import LLMProvider, ModelTier, ToolSpec
from care_lifeline.tools.registry import get_tool

logger = logging.getLogger(__name__)

# 单轮对话内允许的最大「模型↔工具」往返数，防止工具调用循环失控。
_MAX_TOOL_ROUNDS = 3
# 工具结果回填与轨迹摘要的截断长度，避免大结果进入 checkpoint / SSE。
_RESULT_PREVIEW_CHARS = 400
# 轮数耗尽时的兜底文案（不确定的医学场景宁可拒答也不编造）。
_ROUNDS_EXHAUSTED_DRAFT = "抱歉，本次查询暂时未能完成，请稍后重试或直接咨询医师、药师。"


@dataclass(frozen=True)
class ToolAgentConfig:
    """工具智能体的运行参数。

    Attributes:
        system_prompt: 约束模型行为的系统提示词。
        tool_names: 允许调用的工具注册名列表。
        tier: 模型分层（fast/strong）。
        max_rounds: 最大模型↔工具往返数。
    """

    system_prompt: str
    tool_names: tuple[str, ...]
    tier: ModelTier = "strong"
    max_rounds: int = _MAX_TOOL_ROUNDS


@dataclass(frozen=True)
class ToolAgentOutcome:
    """工具智能体的执行结果。

    Attributes:
        draft: 最终回答文本（轮数耗尽时为兜底文案）。
        traces: 本轮产生的真实工具调用轨迹，按调用顺序排列。
    """

    draft: str
    traces: list[ToolTrace] = field(default_factory=list)


def _spec_of(name: str) -> ToolSpec | None:
    """从注册表取工具并转成 schema 描述；未注册返回 ``None``。"""
    tool = get_tool(name)
    if tool is None:
        return None
    return ToolSpec(name=tool.name, description=tool.description, parameters=tool.parameters)


async def run_tool_agent(
    state: AgentState, provider: LLMProvider, config: ToolAgentConfig
) -> ToolAgentOutcome:
    """跑一轮完整的 ReAct 工具循环。

    Args:
        state: 当前图状态（取用户消息作循环起点）。
        provider: 提供 ``invoke_with_tools`` 的 LLM 提供者。
        config: 系统提示词与工具白名单等运行参数。

    Returns:
        最终回答与真实工具轨迹；中间消息（工具结果等）只留在循环内部，
        不写回图状态，保持会话历史干净。
    """
    tools = [spec for name in config.tool_names if (spec := _spec_of(name)) is not None]
    convo: list[BaseMessage] = [
        SystemMessage(content=config.system_prompt),
        *state["messages"],
    ]
    traces: list[ToolTrace] = []
    for _ in range(config.max_rounds):
        ai = await asyncio.to_thread(
            provider.invoke_with_tools, messages=convo, tools=tools, tier=config.tier
        )
        calls = ai.tool_calls or []
        if not calls:
            return ToolAgentOutcome(draft=str(ai.content), traces=traces)
        convo.append(ai)
        for call in calls:
            trace, reply = await _execute(call)
            traces.append(trace)
            convo.append(reply)
    logger.warning(
        "tool_agent_rounds_exhausted",
        extra={"tools": list(config.tool_names), "max_rounds": config.max_rounds},
    )
    return ToolAgentOutcome(draft=_ROUNDS_EXHAUSTED_DRAFT, traces=traces)


async def _execute(call: ToolCall) -> tuple[ToolTrace, ToolMessage]:
    """执行单次工具调用，返回轨迹与回填给模型的 ``ToolMessage``。

    Args:
        call: AIMessage.tool_calls 中的一项（含 name/args/id）。

    Returns:
        (轨迹, 工具结果消息)；工具不存在或执行异常都会转成 ``ok=False``
        的轨迹与错误结果消息，让模型有机会改述而不是整轮失败。
    """
    name = call.get("name", "")
    args = dict(call.get("args") or {})
    call_id = call.get("id") or ""
    tool = get_tool(name)
    if tool is None:
        trace = ToolTrace(tool=name, args=args, ok=False, error="未注册的工具")
        return trace, _tool_message({"ok": False, "error": "unknown_tool"}, call_id)

    start = time.perf_counter()
    try:
        result = await tool.run(**args)
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        logger.warning(
            "tool_execution_failed",
            extra={"tool": name, "error_type": type(exc).__name__},
        )
        trace = ToolTrace(tool=name, args=args, ok=False, error=str(exc), latency_ms=latency)
        return trace, _tool_message({"ok": False, "error": str(exc)}, call_id)

    latency = (time.perf_counter() - start) * 1000
    payload = {"ok": result.ok, "data": result.data, "error": result.error}
    trace = ToolTrace(
        tool=name,
        args=args,
        ok=result.ok,
        error=result.error,
        latency_ms=latency,
        summary=json.dumps(result.data, ensure_ascii=False, default=str)[:_RESULT_PREVIEW_CHARS],
    )
    return trace, _tool_message(payload, call_id)


def _tool_message(payload: dict[str, object], call_id: str) -> ToolMessage:
    """把工具结果序列化为回填消息；不可序列化字段降级为字符串。"""
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False, default=str),
        tool_call_id=call_id,
    )
