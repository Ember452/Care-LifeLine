from care_lifeline.graph.state import AgentState, last_user_text

EMERGENCY_KEYWORDS = (
    "胸痛",
    "呼吸困难",
    "卒中",
    "中风",
    "昏迷",
    "大出血",
    "窒息",
    "休克",
)

REPORT_KEYWORDS = (
    "化验",
    "报告",
    "指标",
    "参考范围",
    "升高",
    "偏低",
    "贫血",
    "血糖",
    "血压",
    "肌酐",
    "转氨酶",
)

MEDICATION_KEYWORDS = (
    "相互作用",
    "用药",
    "药物冲突",
    "一起吃",
    "同时吃",
    "配伍",
    "联合用药",
)


def classify_intent(text: str) -> tuple[str, str]:
    """Return ``(risk_level, intent)`` from the latest user message."""
    if any(keyword in text for keyword in EMERGENCY_KEYWORDS):
        return "critical", "emergency"
    if any(keyword in text for keyword in MEDICATION_KEYWORDS):
        return "routine", "medication"
    if any(keyword in text for keyword in REPORT_KEYWORDS):
        return "routine", "report"
    return "routine", "triage"


def router_node(state: AgentState, provider) -> dict:
    risk_level, intent = classify_intent(last_user_text(state["messages"]))
    return {
        "intent": intent,
        "risk_level": risk_level,
        "hitl_required": risk_level == "critical",
    }
