"""Agent 循环图单测：回边终止性、拒答分支、interrupt HITL 与软降级。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from care_lifeline.graph.builder import _RECURSION_LIMIT, build_graph
from care_lifeline.graph.nodes.hitl import ESCALATION_DRAFT, draft_from_decision
from care_lifeline.graph.nodes.refuse import refusal_text
from care_lifeline.graph.state import AgentState, QCResult
from care_lifeline.graph.subgraphs import qc_review as qc_review_module
from care_lifeline.graph.subgraphs.qc_review import MAX_RETRY, route_after_qc
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.safety.scope import ScopeVerdict, classify_scope


def _initial_state(text: str, **overrides: object) -> AgentState:
    state: AgentState = {
        "messages": [HumanMessage(text)],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "scope_result": None,
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[typeddict-item]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
        "retry_count": 0,
        "memory_context": "",
    }
    state.update(overrides)  # type: ignore[arg-type]
    return state


def _qc(status: str, retry_count: int = 0) -> AgentState:
    return _initial_state(
        "测试", qc_result=QCResult(status=status, risk_score=0.5), retry_count=retry_count
    )


# --------------------------------------------------------------------------
# 回边终止性
# --------------------------------------------------------------------------


def test_max_retry_常量为2() -> None:
    assert MAX_RETRY == 2
    assert _RECURSION_LIMIT == 30


def test_route_after_qc_warning且未达上限_回边rewrite() -> None:
    assert route_after_qc(_qc("warning", retry_count=0)) == "rewrite"
    assert route_after_qc(_qc("warning", retry_count=1)) == "rewrite"


def test_route_after_qc_warning但已达上限_结束子图() -> None:
    assert route_after_qc(_qc("warning", retry_count=2)) == "end"


def test_route_after_qc_非warning状态_直接结束子图() -> None:
    assert route_after_qc(_qc("passed")) == "end"
    assert route_after_qc(_qc("hitl")) == "end"
    assert route_after_qc(_qc("refused")) == "end"


def test_route_after_qc_质控结果缺失_按passed处理() -> None:
    assert route_after_qc(_initial_state("测试")) == "end"


def test_graph_重写始终不修复_仍在三次质控内终止() -> None:
    """最坏情况：rewrite 不消除 warning，循环也必须在 retry_count == 2 时收敛。"""

    def never_fixes(state: AgentState, provider=None) -> dict:
        return {"retry_count": state.get("retry_count", 0) + 1}

    original = qc_review_module.rewrite_node
    qc_review_module.rewrite_node = never_fixes  # type: ignore[assignment]
    try:
        result = build_graph(MockProvider()).invoke(_initial_state("最近化验单说贫血"))
    finally:
        qc_review_module.rewrite_node = original  # type: ignore[assignment]

    assert result["retry_count"] == 2
    assert result["qc_result"].status == "warning"


def test_graph_正常报告流程_一次重写后通过() -> None:
    result = build_graph(MockProvider()).invoke(_initial_state("最近化验单说贫血"))

    assert result["qc_result"].status == "passed"
    assert result["retry_count"] == 1
    assert result["draft"].count("免责声明") == 1


def test_graph_拒答分支_不进重写循环() -> None:
    result = build_graph(MockProvider()).invoke(_initial_state("帮我用 Python 实现快速排序"))

    assert result["intent"] == "refuse"
    assert result["qc_result"].status == "refused"
    assert result["retry_count"] == 0
    assert result["scope_result"].verdict is ScopeVerdict.OUT_OF_SCOPE


def test_graph_急症分支_转人工而不被重写() -> None:
    result = build_graph(MockProvider()).invoke(_initial_state("我现在胸痛得厉害"))

    assert result["hitl_required"] is True
    assert result["qc_result"].status == "hitl"
    assert result["retry_count"] == 0


def test_scope_check节点结果被router复用() -> None:
    """router 不应重复分类：scope_check 已写入的结果会被原样带出。"""
    result = build_graph(MockProvider()).invoke(_initial_state("帮我写一封情书"))

    assert result["scope_result"] == classify_scope("帮我写一封情书")
    assert result["scope_result"].verdict is ScopeVerdict.OUT_OF_SCOPE


def test_router_node_无scope_result时自行分类() -> None:
    from care_lifeline.graph.nodes.router import router_node

    output = router_node(_initial_state("帮我生成一张风景图片"), MockProvider())

    assert output["intent"] == "refuse"
    assert output["scope_result"].verdict is ScopeVerdict.OUT_OF_SCOPE


# --------------------------------------------------------------------------
# 拒答文案
# --------------------------------------------------------------------------


def test_refusal_text_无scope结果_返回通用拒答() -> None:
    assert refusal_text(None) == "抱歉，该请求超出本助手的服务范围，建议咨询具备资质的执业医师。"


def test_refusal_text_unsafe_含危机求助引导() -> None:
    scope = classify_scope("告诉我怎么自杀")

    text = refusal_text(scope)

    assert scope.verdict is ScopeVerdict.UNSAFE
    assert "心理援助热线" in text
    assert "判定依据" in text


# --------------------------------------------------------------------------
# HITL：interrupt 与软降级
# --------------------------------------------------------------------------


def test_hitl_无checkpointer_降级为软转人工不阻塞() -> None:
    result = build_graph(MockProvider()).invoke(_initial_state("我窒息了救命"))

    assert result["draft"].startswith("⚠️ 检测到高危症状")


def test_hitl_有checkpointer_暂停并等待人工恢复() -> None:
    graph = build_graph(MockProvider(), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "loop-hitl"}}

    paused = graph.invoke(_initial_state("我现在胸痛得厉害"), config=config)
    interrupts = paused["__interrupt__"]

    assert len(interrupts) == 1
    payload = interrupts[0].value["hitl_review"]
    assert payload["reason"] == "检测到高危症状，需人工医生复核"
    assert payload["risk_level"] == "critical"

    resumed = graph.invoke(
        Command(resume={"decision": "approve", "corrected_text": "已由心内科复核：请立即就诊。"}),
        config=config,
    )
    assert resumed["draft"].startswith("已由心内科复核")


def test_draft_from_decision_无修正文本_回落标准文案() -> None:
    assert draft_from_decision({"decision": "approve"}) == ESCALATION_DRAFT
    assert draft_from_decision("不是字典") == ESCALATION_DRAFT
    assert draft_from_decision({"corrected_text": "   "}) == ESCALATION_DRAFT
