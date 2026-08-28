from __future__ import annotations

from langchain_core.messages import HumanMessage

from care_lifeline.graph.nodes.report_interpreter import report_interpreter_node
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider


def _state(text: str) -> AgentState:
    return AgentState(
        messages=[HumanMessage(text)],
        patient_id=None,
        intent="report",
        risk_level="routine",
        citations=[],
        draft="",
        qc_result=None,
        hitl_required=False,
        report=None,
    )


def test_node_returns_structured_report() -> None:
    out = report_interpreter_node(_state("血压：150/95（参考 90-140）"), MockProvider())
    assert out["report"] is not None
    assert out["report"].fields
    assert out["draft"]
    assert "报告解读" in out["draft"]
