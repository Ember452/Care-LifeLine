import asyncio

from langchain_core.messages import HumanMessage

from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.nodes.medication import medication_node
from care_lifeline.graph.nodes.router import classify_intent
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider


def _initial(text: str) -> AgentState:
    return {
        "messages": [HumanMessage(text)],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
    }


def test_classify_intent_medication() -> None:
    risk, intent = classify_intent("华法林和阿司匹林的相互作用")
    assert intent == "medication"
    assert risk == "routine"


def test_medication_node_returns_warnings() -> None:
    out = medication_node(_initial("华法林 阿司匹林 一起吃"), None)
    assert out["medication_warnings"]


def test_graph_medication_flow_includes_warning_in_draft() -> None:
    state = asyncio.run(
        build_graph(MockProvider()).ainvoke(_initial("华法林，阿司匹林 一起吃有相互作用吗"))
    )
    assert state["medication_warnings"]
    assert "用药警示" in state["draft"]


def test_graph_medication_flow_with_separators() -> None:
    state = asyncio.run(
        build_graph(MockProvider()).ainvoke(_initial("华法林，阿司匹林 一起吃有相互作用吗"))
    )
    assert state["medication_warnings"]
    assert "用药警示" in state["draft"]
