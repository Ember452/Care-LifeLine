"""质控评审子图（graph/subgraphs/qc_review.py）的结构与行为测试。"""

import asyncio

from langchain_core.messages import HumanMessage

from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.state import AgentState
from care_lifeline.graph.subgraphs.qc_review import build_qc_review_subgraph
from care_lifeline.llm.mock_provider import MockProvider


def _initial(text: str) -> AgentState:
    return {
        "messages": [HumanMessage(text)],
        "patient_id": None,
        "intent": "triage",
        "risk_level": "routine",
        "citations": [],
        "draft": "建议多休息，若持续发热请及时就医。",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
        "retry_count": 0,
        "memory_context": "",
    }


def test_主图包含子图节点_不再含qc与rewrite() -> None:
    graph = build_graph(MockProvider())
    node_names = set(graph.get_graph().nodes)
    assert "qc_review" in node_names
    assert "qc" not in node_names
    assert "rewrite" not in node_names


def test_子图独立运行_补全免责声明并通过质控() -> None:
    """无免责声明的草稿经 warning → rewrite 一轮后通过。"""
    subgraph = build_qc_review_subgraph(MockProvider())
    result = asyncio.run(subgraph.ainvoke(_initial("最近化验单说贫血")))

    assert result["qc_result"] is not None
    assert result["qc_result"].status == "passed"
    assert result["retry_count"] == 1
    assert "免责声明" in result["draft"]


def test_子图运行后上游状态字段原样保留() -> None:
    """子图与主图共享 AgentState：不进质控逻辑的字段不能丢失。"""
    state = _initial("最近化验单说贫血")
    state["citations"] = []  # 保持初始
    subgraph = build_qc_review_subgraph(MockProvider())
    result = asyncio.run(subgraph.ainvoke(state))

    assert result["messages"] == state["messages"]
    assert result["intent"] == "triage"
    assert result["memory_context"] == ""
