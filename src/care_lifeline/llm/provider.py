from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from langchain_core.messages import AIMessage, BaseMessage

from care_lifeline.config import Settings, get_settings

# 模型分层：fast 走轻量模型（分类/分诊），strong 走旗舰模型（解读/质控）。
ModelTier = Literal["fast", "strong"]


@dataclass(frozen=True)
class TokenUsage:
    """单次 LLM 调用的 token 用量（可观测性的成本数据源）。

    Attributes:
        input_tokens: 输入 token 数。
        output_tokens: 输出 token 数。
        estimated: 是否为估算值——真实 usage 缺失（如 mock 模式）时
            按字符数启发式估算并显式标记，避免与真实计量混淆。
    """

    input_tokens: int
    output_tokens: int
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def estimate_usage(input_text: str, output_text: str) -> TokenUsage:
    """按字符数启发式估算 token 用量（约 2 字符/token），标记 ``estimated``。

    仅用于 mock 模式或真实 usage 缺失时的管线演示，不代表真实计量。
    """
    return TokenUsage(
        input_tokens=max(len(input_text) // 2, 0),
        output_tokens=max(len(output_text) // 2, 0),
        estimated=True,
    )


@dataclass(frozen=True)
class ToolSpec:
    """工具的 JSON Schema 描述，供 LLM 原生 tool-calling 选择工具。

    Attributes:
        name: 工具名（与 ``tools.registry`` 注册名一致）。
        description: 功能描述，模型据此决定是否调用。
        parameters: 参数的 JSON Schema（OpenAI function calling 格式）。
    """

    name: str
    description: str
    parameters: dict[str, Any]


@runtime_checkable
class LLMProvider(Protocol):
    """Unified LLM interface for the dual-mode (mock / real) backend.

    实现方须维护 ``last_usage``：最近一次调用的 token 用量（``None`` 表示
    尚未调用），供可观测性层采集成本数据。
    """

    last_usage: TokenUsage | None

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> str:
        """Return a single completion for the given chat messages."""
        ...

    def stream(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> Iterator[str]:
        """Yield incremental completion chunks for the given chat messages."""
        ...

    def invoke_with_tools(
        self,
        *,
        messages: list[BaseMessage],
        tools: list[ToolSpec],
        temperature: float = 0.2,
        tier: ModelTier = "strong",
    ) -> AIMessage:
        """执行一轮原生 tool-calling。

        Args:
            messages: LangChain 消息序列（含 ``ToolMessage`` 时表示工具结果回填轮）。
            tools: 可选工具的 schema 描述。
            temperature: 采样温度。
            tier: 模型分层。

        Returns:
            可能携带 ``tool_calls`` 的 AIMessage；无 ``tool_calls`` 表示模型给出最终回答。
        """
        ...


def make_provider(settings: Settings | None = None) -> LLMProvider:
    """Return a provider based on the configured ``llm_mode``."""
    from care_lifeline.llm.mock_provider import MockProvider
    from care_lifeline.llm.real_provider import RealProvider

    resolved = settings or get_settings()
    if resolved.llm_mode == "real":
        return RealProvider(resolved)
    return MockProvider()
