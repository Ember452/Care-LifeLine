"""质控评审子图：「qc → warning 重写 → 再质控」回环的封装（ADR-0015）。

把质控循环收敛为单个子图节点后，主图拓扑简化为
``上游节点 → qc_review → responder``，主图不再感知重写细节；
重试上限（``MAX_RETRY``）与收敛保证留在子图内部。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from care_lifeline.graph.nodes.qc import qc_node
from care_lifeline.graph.nodes.rewrite import rewrite_node
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import LLMProvider

# 重写上限：qc 判 warning 时最多回边重写 2 次（共 3 次质控），之后强制收口。
MAX_RETRY = 2


def route_after_qc(state: AgentState) -> str:
    """质控出口：warning 且未达重写上限时回边 rewrite，否则结束子图。"""
    qc = state.get("qc_result")
    status = qc.status if qc is not None else "passed"
    should_rewrite = status == "warning" and state.get("retry_count", 0) < MAX_RETRY
    return "rewrite" if should_rewrite else "end"


def build_qc_review_subgraph(provider: LLMProvider):
    """编译质控评审子图。

    Args:
        provider: LLM 提供者（qc 节点 real 模式下做语义评审）。

    Returns:
        编译后的子图，可作为主图节点直接注册。
    """
    graph = StateGraph(AgentState)
    graph.add_node("qc", lambda s: qc_node(s, provider))
    graph.add_node("rewrite", rewrite_node)
    graph.add_edge(START, "qc")
    graph.add_conditional_edges("qc", route_after_qc, {"rewrite": "rewrite", "end": END})
    graph.add_edge("rewrite", "qc")
    return graph.compile()
