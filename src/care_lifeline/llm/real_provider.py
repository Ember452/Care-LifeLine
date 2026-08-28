from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import SecretStr

from care_lifeline.config import Settings


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
    """

    def __init__(self, settings: Settings) -> None:
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

    def complete(self, *, messages: list[dict], temperature: float = 0.2) -> str:
        response = self._flagship.invoke(_to_lc_messages(messages))
        return str(response.content)

    def stream(self, *, messages: list[dict], temperature: float = 0.2) -> Iterator[str]:
        for chunk in self._flagship.stream(_to_lc_messages(messages)):
            if chunk.content:
                yield str(chunk.content)
