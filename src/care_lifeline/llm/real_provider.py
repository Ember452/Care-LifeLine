import os
from collections.abc import Iterator

from pydantic import SecretStr

from care_lifeline.config import Settings


class RealProvider:
    """Provider backed by a real LLM via ``langchain-openai``.

    Supports model-tier routing (mini for triage, flagship for interpretation).
    Construction fails fast when no API key is configured, prompting the user to
    switch to mock mode.
    """

    def __init__(self, settings: Settings) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未配置 LLM API Key（OPENAI_API_KEY）。"
                "请设置环境变量，或将 CARE_LLM_MODE 设为 mock。"
            )
        from langchain_openai import ChatOpenAI

        secret = SecretStr(api_key)
        self._mini = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=secret)
        self._flagship = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=secret)

    def complete(self, *, messages: list[dict], temperature: float = 0.2) -> str:
        response = self._flagship.invoke(_to_lc_messages(messages))
        return str(response.content)

    def stream(self, *, messages: list[dict], temperature: float = 0.2) -> Iterator[str]:
        for chunk in self._flagship.stream(_to_lc_messages(messages)):
            if chunk.content:
                yield str(chunk.content)


def _to_lc_messages(messages: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"]} for m in messages]
