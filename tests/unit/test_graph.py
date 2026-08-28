from langchain_core.messages import HumanMessage

from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider


def _initial_state(text: str) -> AgentState:
    return {
        "messages": [HumanMessage(text)],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "scope_result": None,
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[typeddict-item]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
        "retry_count": 0,
        "memory_context": "",
    }


def test_report_flow_produces_draft_citations_and_passes() -> None:
    graph = build_graph(MockProvider())
    result = graph.invoke(_initial_state("最近化验单说贫血"))

    assert result["draft"]
    assert result["citations"]
    assert result["qc_result"].status == "passed"


def test_emergency_triggers_hitl() -> None:
    graph = build_graph(MockProvider())
    result = graph.invoke(_initial_state("我现在胸痛得厉害"))

    assert result["hitl_required"] is True
    assert result["qc_result"].status == "hitl"


def test_out_of_scope_is_refused() -> None:
    graph = build_graph(MockProvider())
    result = graph.invoke(_initial_state("帮我用 Python 实现快速排序"))

    assert result["intent"] == "refuse"
    assert result["qc_result"].status == "refused"
    assert result["scope_result"].verdict == "out_of_scope"
