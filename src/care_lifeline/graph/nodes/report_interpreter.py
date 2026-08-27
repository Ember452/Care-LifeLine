from care_lifeline.graph.state import AgentState, Citation, last_user_text


def report_interpreter_node(state: AgentState, provider) -> dict:
    text = last_user_text(state["messages"])
    draft = provider.complete(messages=[{"role": "user", "content": text}])
    citation = Citation(
        index=0,
        source="临床检验指南",
        snippet="请结合参考范围判断指标偏高/偏低，并由医生综合病史评估。",
    )
    return {"draft": draft, "citations": [citation]}
