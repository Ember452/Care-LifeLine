from care_lifeline.config import get_settings
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.llm.provider import make_provider
from care_lifeline.llm.real_provider import RealProvider


def test_make_provider_returns_mock_by_default() -> None:
    get_settings.cache_clear()
    assert isinstance(make_provider(), MockProvider)


def test_make_provider_real_with_key_is_realprovider(monkeypatch) -> None:
    monkeypatch.setenv("CARE_LLM_MODE", "real")
    monkeypatch.setenv("CARE_LLM_API_KEY", "sk-test-placeholder")
    get_settings.cache_clear()
    provider = make_provider()
    assert isinstance(provider, RealProvider)


def test_real_provider_requires_key(monkeypatch) -> None:
    monkeypatch.setenv("CARE_LLM_MODE", "real")
    monkeypatch.setenv("CARE_LLM_API_KEY", "")
    get_settings.cache_clear()
    import pytest

    with pytest.raises(RuntimeError):
        RealProvider(get_settings())
