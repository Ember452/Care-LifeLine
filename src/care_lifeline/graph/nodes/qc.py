from care_lifeline.graph.state import AgentState, QCResult


def qc_node(state: AgentState, provider) -> dict:
    """Minimal rule-based QC (placeholder for the M2 rules engine)."""
    if state.get("hitl_required"):
        result = QCResult(
            status="hitl",
            risk_score=0.95,
            violations=["检测到高风险症状，转人工复核"],
        )
    elif not state.get("draft"):
        result = QCResult(
            status="refused",
            risk_score=0.9,
            violations=["无法生成安全回复"],
        )
    else:
        result = QCResult(status="passed", risk_score=0.1, violations=[])
    return {"qc_result": result}
