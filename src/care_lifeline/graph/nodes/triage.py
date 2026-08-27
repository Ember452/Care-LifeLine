from care_lifeline.graph.state import AgentState, last_user_text


def triage_node(state: AgentState, provider) -> dict:
    text = last_user_text(state["messages"])
    draft = provider.complete(messages=[{"role": "user", "content": text}])
    return {"draft": draft}
