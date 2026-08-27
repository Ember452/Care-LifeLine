from care_lifeline.llm.mock_provider import MockProvider


def test_complete_returns_nonempty() -> None:
    provider = MockProvider()
    out = provider.complete(messages=[{"role": "user", "content": "我最近持续咳嗽"}])
    assert isinstance(out, str)
    assert out


def test_stream_yields_chunks() -> None:
    provider = MockProvider()
    chunks = list(provider.stream(messages=[{"role": "user", "content": "我最近持续咳嗽"}]))
    assert len(chunks) >= 1
    assert "".join(chunks)


def test_emergency_keyword_triggers_ed_tip() -> None:
    provider = MockProvider()
    out = provider.complete(messages=[{"role": "user", "content": "我现在胸痛得厉害"}])
    assert "急诊" in out
