from collections.abc import Iterator
from typing import Literal, Protocol, runtime_checkable

from care_lifeline.config import Settings, get_settings

# 模型分层：fast 走轻量模型（分类/分诊），strong 走旗舰模型（解读/质控）。
ModelTier = Literal["fast", "strong"]


@runtime_checkable
class LLMProvider(Protocol):
    """Unified LLM interface for the dual-mode (mock / real) backend."""

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> str:
        """Return a single completion for the given chat messages."""
        ...

    def stream(
        self, *, messages: list[dict], temperature: float = 0.2, tier: ModelTier = "strong"
    ) -> "Iterator[str]":
        """Yield incremental completion chunks for the given chat messages."""
        ...


def make_provider(settings: Settings | None = None) -> LLMProvider:
    """Return a provider based on the configured ``llm_mode``."""
    from care_lifeline.llm.mock_provider import MockProvider
    from care_lifeline.llm.real_provider import RealProvider

    resolved = settings or get_settings()
    if resolved.llm_mode == "real":
        return RealProvider(resolved)
    return MockProvider()
