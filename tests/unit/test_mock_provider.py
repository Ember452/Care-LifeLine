import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.llm.provider import ToolSpec

_DDI_SPEC = ToolSpec(
    name="drug_interaction", description="查相互作用", parameters={"type": "object"}
)


def _tool_result_message(payload: dict) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False), tool_call_id="call_mock_0"
    )


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


def test_invoke_with_tools_first_round_requests_tool_call() -> None:
    provider = MockProvider()
    ai = provider.invoke_with_tools(
        messages=[HumanMessage("华法林和阿司匹林能一起吃吗")], tools=[_DDI_SPEC]
    )
    assert len(ai.tool_calls) == 1
    call = ai.tool_calls[0]
    assert call["name"] == "drug_interaction"
    assert call["args"] == {"drugs": "华法林和阿司匹林能一起吃吗"}
    assert call["id"] == "call_mock_0"


def test_invoke_with_tools_answers_from_tool_result_with_hits() -> None:
    provider = MockProvider()
    hits = [{"a": "华法林", "b": "阿司匹林", "severity": "major", "note": "出血风险"}]
    call = {"name": "drug_interaction", "args": {}, "id": "call_mock_0", "type": "tool_call"}
    ai = provider.invoke_with_tools(
        messages=[
            HumanMessage("华法林和阿司匹林"),
            AIMessage(content="", tool_calls=[call]),
            _tool_result_message({"ok": True, "data": {"interactions": hits}}),
        ],
        tools=[_DDI_SPEC],
    )
    assert not ai.tool_calls
    assert "华法林 + 阿司匹林" in ai.content
    assert "major" in ai.content
    assert "咨询医师或药师" in ai.content


def test_invoke_with_tools_answers_no_hits() -> None:
    provider = MockProvider()
    ai = provider.invoke_with_tools(
        messages=[
            HumanMessage("维生素 C 和维生素 E 能一起吃吗"),
            _tool_result_message({"ok": True, "data": {"interactions": []}}),
        ],
        tools=[_DDI_SPEC],
    )
    assert "未查询到" in ai.content
    assert "引用自" in ai.content


def test_invoke_with_tools_tool_failure_told_honestly() -> None:
    provider = MockProvider()
    ai = provider.invoke_with_tools(
        messages=[
            HumanMessage("华法林和阿司匹林"),
            _tool_result_message({"ok": False, "data": {}, "error": "下游超时"}),
        ],
        tools=[_DDI_SPEC],
    )
    assert "暂时不可用" in ai.content


def test_invoke_with_tools_without_relevant_tool_answers_directly() -> None:
    provider = MockProvider()
    other_spec = ToolSpec(name="metric_trend", description="查趋势", parameters={"type": "object"})
    ai = provider.invoke_with_tools(
        messages=[HumanMessage("我最近有点头晕")], tools=[other_spec]
    )
    assert not ai.tool_calls
    assert "症状" in ai.content
