from care_lifeline.graph.state import AgentState, Citation

DISCLAIMER = "\n\n（免责声明：本回复仅供参考，不替代执业医师的诊断与治疗建议。）"


def responder_node(state: AgentState, provider) -> dict:
    body = state.get("draft", "")
    citations: list[Citation] = state.get("citations", [])
    if citations:
        refs = "\n".join(f"[{c.index}] {c.source}：{c.snippet}" for c in citations)
        body = f"{body}\n\n参考：\n{refs}"
    body = f"{body}{DISCLAIMER}"
    return {"draft": body}
