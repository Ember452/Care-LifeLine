from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import SecretStr

from care_lifeline.config import Settings
from care_lifeline.llm.provider import ModelTier, TokenUsage, ToolSpec, estimate_usage


def to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    """把 :class:`ToolSpec` 转成 OpenAI function calling 的工具描述格式。"""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def _messages_text(messages: list[dict]) -> str:
    return " ".join(str(m.get("content", "")) for m in messages)


def _lc_messages_text(messages: list[BaseMessage]) -> str:
    return " ".join(str(m.content) for m in messages)


def _to_lc_messages(messages: list[dict]) -> list[BaseMessage]:
    role_map = {
        "system": SystemMessage,
        "user": HumanMessage,
        "assistant": AIMessage,
    }
    out: list[BaseMessage] = []
    for m in messages:
        cls = role_map.get(m.get("role", "user"), HumanMessage)
        out.append(cls(content=m["content"]))
    return out


class RealProvider:
    """Provider backed by a real LLM via an OpenAI-compatible endpoint.

    Defaults target 火山方舟 Doubao; 切换为 DeepSeek 只需改 ``llm_base_url`` /
    ``llm_model`` / ``llm_api_key``（均为 OpenAI 兼容协议）。
    支持模型分层：triage 走 mini，解读/质控走 flagship。
    ``last_usage`` 记录最近一次调用的 token 用量：优先取响应的
    ``usage_metadata``（真实计量），流式缺失时按字符估算（标记 estimated）。
    """

    last_usage: TokenUsage | None

    def __init__(self, settings: Settings) -> None:
        self.last_usage = None
        if not settings.llm_api_key:
            raise RuntimeError(
                "未配置 LLM API Key（CARE_LLM_API_KEY）。"
                "请设置环境变量（占位示例 sk-......），或将 CARE_LLM_MODE 设为 mock。"
            )
        from langchain_openai import ChatOpenAI

        secret = SecretStr(settings.llm_api_key)
        common: dict[str, Any] = {
            "base_url": settings.llm_base_url,
            "api_key": secret,
            "temperature": 0.2,
            "streaming": True,
        }
        self._mini = ChatOpenAI(model=settings.llm_model_mini, **common)
        self._flagship = ChatOpenAI(model=settings.llm_model, **common)

    def _client(self, tier: ModelTier):
        """按分层返回模型客户端：fast 走 mini（分类/分诊），strong 走旗舰（解读/质控）。"""
        return self._mini if tier == "fast" else self._flagship

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> str:
        # temperature 入参生效（P2-G）：默认 0.2，调用方可按场景覆盖。
        response = (
            self._client(tier).bind(temperature=temperature).invoke(_to_lc_messages(messages))
        )
        content = str(response.content)
        self._track_usage(response, _messages_text(messages), content)
        return content

    def stream(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> Iterator[str]:
        chunks: list[str] = []
        for chunk in (
            self._client(tier).bind(temperature=temperature).stream(_to_lc_messages(messages))
        ):
            if chunk.content:
                chunks.append(str(chunk.content))
                yield str(chunk.content)
        self._track_usage(None, _messages_text(messages), "".join(chunks))

    def _track_usage(self, response: object, input_text: str, output_text: str) -> None:
        """记录用量：优先响应自带的 usage_metadata，缺失时字符估算。"""
        metadata = getattr(response, "usage_metadata", None) if response is not None else None
        if isinstance(metadata, dict) and "input_tokens" in metadata:
            self.last_usage = TokenUsage(
                input_tokens=int(metadata.get("input_tokens", 0)),
                output_tokens=int(metadata.get("output_tokens", 0)),
                estimated=False,
            )
        else:
            self.last_usage = estimate_usage(input_text, output_text)

    def invoke_with_tools(
        self,
        *,
        messages: list[BaseMessage],
        tools: list[ToolSpec],
        temperature: float = 0.2,
        tier: ModelTier = "strong",
    ) -> AIMessage:
        """一轮原生 tool-calling：模型返回的 AIMessage 可能携带 ``tool_calls``。"""
        response = (
            self._client(tier)
            .bind_tools([to_openai_tool(spec) for spec in tools])
            .bind(temperature=temperature)
            .invoke(messages)
        )
        if not isinstance(response, AIMessage):
            raise RuntimeError(f"tool-calling 返回了非 AIMessage 类型: {type(response).__name__}")
        self._track_usage(response, _lc_messages_text(messages), str(response.content))
        return response
