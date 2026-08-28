from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.safety.scope import ScopeResult, ScopeVerdict

REFUSAL_TEMPLATES: dict[ScopeVerdict, str] = {
    ScopeVerdict.OUT_OF_SCOPE: (
        "抱歉，我只能协助医疗健康相关的问题（症状分诊、报告解读、用药咨询、慢病管理），"
        "这个问题不在服务范围内。"
    ),
    ScopeVerdict.RESTRICTED: (
        "抱歉，开具处方、作出诊断结论或出具医学证明/鉴定都需要执业医师面诊后完成，"
        "本助手无法提供。建议您携带相关资料到相应科室就诊。"
    ),
    ScopeVerdict.UNSAFE: (
        "抱歉，您描述的内容涉及可能危害自身或他人安全的情形，我无法提供协助。"
        "如果您正处于情绪危机中，请立即联系当地心理援助热线，或前往最近医院急诊科寻求帮助。"
    ),
}

_FALLBACK_REFUSAL = "抱歉，该请求超出本助手的服务范围，建议咨询具备资质的执业医师。"


def refusal_text(scope: ScopeResult | None) -> str:
    """按 scope 判定结果生成拒答文案（含判定依据，便于审计与 SSE 展示）。

    Args:
        scope: 输入侧的范围判定结果；为 ``None`` 时返回通用拒答文案。

    Returns:
        面向用户的拒答文本。
    """
    if scope is None:
        return _FALLBACK_REFUSAL
    template = REFUSAL_TEMPLATES.get(scope.verdict, _FALLBACK_REFUSAL)
    return f"{template}\n（判定依据：{scope.reason}）"


def refuse_node(state: AgentState, provider: LLMProvider | None = None) -> dict[str, object]:
    """产出拒答草稿，随后仍要过质控（契约 §2.3：refuse → qc → responder）。"""
    return {"draft": refusal_text(state.get("scope_result")), "intent": "refuse"}
