from __future__ import annotations

from care_lifeline.graph.nodes.qc import qc_node
from care_lifeline.graph.state import AgentState, QCResult


def _state(draft: str, risk_level: str = "routine") -> AgentState:
    return AgentState(
        messages=[],
        patient_id=None,
        intent="triage",
        risk_level=risk_level,
        citations=[],
        draft=draft,
        qc_result=None,
        hitl_required=False,
    )


def test_qc_emergency_blocks_and_escalates() -> None:
    out = qc_node(_state("患者胸痛需处理", "critical"), None)
    assert out["qc_result"].status == "hitl"
    assert out["hitl_required"] is True


def test_qc_off_scope_refused() -> None:
    out = qc_node(_state("请帮我开处方药"), None)
    assert out["qc_result"].status == "refused"
    assert out["hitl_required"] is False


def test_qc_clean_passes() -> None:
    out = qc_node(_state("建议多休息。免责声明：仅供参考 [1]", "routine"), None)
    assert out["qc_result"].status == "passed"


def test_qc_empty_refused() -> None:
    out = qc_node(_state(""), None)
    assert out["qc_result"].status == "refused"
    assert isinstance(out["qc_result"], QCResult)
