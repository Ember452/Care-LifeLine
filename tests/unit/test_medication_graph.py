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


def test_medication_node_returns_warnings_and_trace() -> None:
    out = asyncio.run(medication_node(_initial("华法林 阿司匹林 一起吃"), MockProvider()))
    assert out["medication_warnings"]
    assert out["draft"]
    traces = out["tool_traces"]
    assert traces[0].tool == "drug_interaction"
    assert traces[0].ok is True
    assert "相互作用" in out["draft"]


def test_graph_medication_flow_includes_warning_in_draft() -> None:
    state = asyncio.run(
        build_graph(MockProvider()).ainvoke(_initial("华法林，阿司匹林 一起吃有相互作用吗"))
    )
    assert state["medication_warnings"]
    assert "用药警示" in state["draft"]


def test_graph_medication_flow_records_tool_trace() -> None:
    state = asyncio.run(
        build_graph(MockProvider()).ainvoke(_initial("华法林，阿司匹林 一起吃有相互作用吗"))
    )
    traces = state["tool_traces"]
    assert traces[0].tool == "drug_interaction"
    assert traces[0].args["drugs"] == "华法林，阿司匹林 一起吃有相互作用吗"


def test_graph_medication_qc_passes_with_agent_draft() -> None:
    """改造前 medication 节点无 draft，QC 判 refused；现在应基于工具结果通过质控。"""
    state = asyncio.run(
        build_graph(MockProvider()).ainvoke(_initial("华法林，阿司匹林 一起吃有相互作用吗"))
    )
    qc = state["qc_result"]
    assert qc is not None
    assert qc.status == "passed"
    assert "华法林" in state["draft"]
