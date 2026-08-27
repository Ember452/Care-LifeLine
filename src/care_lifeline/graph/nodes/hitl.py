from care_lifeline.graph.state import AgentState


def escalate_node(state: AgentState, provider) -> dict:
    draft = "⚠️ 检测到高危症状，已为您转接人工医生，请保持冷静并尽快前往急诊或拨打急救电话。"
    return {"draft": draft}
