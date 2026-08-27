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
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
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
