from langgraph.graph import END, START, StateGraph

from care_lifeline.graph.nodes.hitl import escalate_node
from care_lifeline.graph.nodes.qc import qc_node
from care_lifeline.graph.nodes.report_interpreter import report_interpreter_node
from care_lifeline.graph.nodes.responder import responder_node
from care_lifeline.graph.nodes.router import router_node
from care_lifeline.graph.nodes.triage import triage_node
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import LLMProvider, make_provider


def _route_after_router(state: AgentState) -> str:
    if state.get("hitl_required"):
        return "hitl"
    intent = state.get("intent", "triage")
    if intent in ("report", "triage"):
        return intent
    return "triage"


def build_graph(provider: LLMProvider | None = None, checkpointer=None):
    """Build the minimal triage graph (M1+).

    ``provider`` defaults to the configured mode (mock in tests/CI).
    ``checkpointer`` enables cross-request conversation recovery (M2-4).
    """
    resolved = provider or make_provider()
    graph = StateGraph(AgentState)

    graph.add_node("router", lambda s: router_node(s, resolved))
    graph.add_node("triage", lambda s: triage_node(s, resolved))
    graph.add_node("report_interpreter", lambda s: report_interpreter_node(s, resolved))
    graph.add_node("qc", lambda s: qc_node(s, resolved))
    graph.add_node("hitl", lambda s: escalate_node(s, resolved))
    graph.add_node("responder", lambda s: responder_node(s, resolved))

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {"hitl": "hitl", "report": "report_interpreter", "triage": "triage"},
    )
    graph.add_edge("triage", "qc")
    graph.add_edge("report_interpreter", "qc")
    graph.add_edge("hitl", "qc")
    graph.add_edge("qc", "responder")
    graph.add_edge("responder", END)

    return graph.compile(checkpointer=checkpointer)
