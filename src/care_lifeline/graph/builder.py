import inspect
import time
from collections.abc import Callable, Hashable
from functools import partial

from langgraph.graph import END, START, StateGraph

from care_lifeline.graph.nodes.hitl import escalate_node
from care_lifeline.graph.nodes.medication import medication_node
from care_lifeline.graph.nodes.memory import memory_recall_node
from care_lifeline.graph.nodes.qc import qc_node
from care_lifeline.graph.nodes.refuse import refuse_node
from care_lifeline.graph.nodes.report_interpreter import report_interpreter_node
from care_lifeline.graph.nodes.responder import responder_node
from care_lifeline.graph.nodes.rewrite import rewrite_node
from care_lifeline.graph.nodes.router import router_node, scope_check_node
from care_lifeline.graph.nodes.triage import triage_node
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import LLMProvider, make_provider

# 重写上限：qc 判 warning 时最多回边重写 2 次（共 3 次质控），之后强制进 responder。
_MAX_RETRY = 2
# 兜底：即使条件边逻辑出错也不会无限循环（LangGraph 超限抛 GraphRecursionError）。
_RECURSION_LIMIT = 30
# 所有会汇聚到质控的上游节点。
_QC_UPSTREAM_NODES = ("triage", "report_interpreter", "medication", "hitl", "refuse")
# 质控出口：warning 且未达重写上限时回边 rewrite，否则收口到 responder。
_QC_ROUTES: dict[Hashable, str] = {"rewrite": "rewrite", "responder": "responder"}


# 节点耗时在状态增量里的键名（SSE/指标层消费；随状态存续，体积仅一个浮点数）。
_TIMING_KEY = "perf_node_ms"


def _timed(name: str, fn: Callable) -> Callable:
    """给节点包一层耗时统计：把毫秒耗时写进状态增量的 ``_TIMING_KEY``。"""
    is_async = inspect.iscoroutinefunction(fn)
    wrapper = _timed_async(fn) if is_async else _timed_sync(fn)
    wrapper.__name__ = f"timed_{name}"
    return wrapper


def _timed_sync(fn: Callable) -> Callable:
    def timed_node(state: AgentState) -> dict:
        start = time.perf_counter()
        return _with_timing(fn(state), start)

    return timed_node


def _timed_async(fn: Callable) -> Callable:
    async def timed_node(state: AgentState) -> dict:
        start = time.perf_counter()
        return _with_timing(await fn(state), start)

    return timed_node


def _with_timing(update: object, start: float) -> dict:
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    if isinstance(update, dict):
        return {**update, _TIMING_KEY: elapsed}
    return {_TIMING_KEY: elapsed}


def _route_after_router(state: AgentState) -> str:
    if state.get("intent") == "refuse":
        return "refuse"
    if state.get("hitl_required"):
        return "hitl"
    intent = state.get("intent", "triage")
    if intent in ("report",):
        return intent
    # triage / medication 先经过 memory_recall 注入患者纵向记忆（P1-F）。
    return "memory_recall"


def _route_after_memory(state: AgentState) -> str:
    return "medication" if state.get("intent") == "medication" else "triage"


def _route_after_qc(state: AgentState) -> str:
    qc = state.get("qc_result")
    status = qc.status if qc is not None else "passed"
    should_rewrite = status == "warning" and state.get("retry_count", 0) < _MAX_RETRY
    return "rewrite" if should_rewrite else "responder"


def build_graph(provider: LLMProvider | None = None, checkpointer=None):
    """Build the triage graph as a cyclic agent loop (契约 §4).

    ``START → scope_check → router → {hitl|refuse|report|memory_recall} → qc``，
    其中 triage / medication 先经 ``memory_recall`` 注入患者纵向记忆（P1-F）；
    qc 判 warning 且未达重写上限时回边到 ``rewrite`` 再次质控，否则进 ``responder``。

    Args:
        provider: LLM 提供者，默认按配置的 ``llm_mode`` 创建。
        checkpointer: 非 ``None`` 时启用会话持久化，并让 ``hitl`` 节点走真 interrupt。

    Returns:
        已编译并带 ``recursion_limit`` 兜底的 LangGraph 图。
    """
    resolved = provider or make_provider()
    interrupt_enabled = checkpointer is not None
    graph = StateGraph(AgentState)

    # 所有节点经 _timed 包装，把单节点耗时写进状态增量（可观测性数据源）。
    graph.add_node("scope_check", _timed("scope_check", lambda s: scope_check_node(s, resolved)))
    graph.add_node("router", _timed("router", lambda s: router_node(s, resolved)))
    graph.add_node("memory_recall", _timed("memory_recall", memory_recall_node))
    graph.add_node("triage", _timed("triage", lambda s: triage_node(s, resolved)))
    graph.add_node(
        "report_interpreter",
        _timed("report_interpreter", lambda s: report_interpreter_node(s, resolved)),
    )
    # medication 为异步节点（ReAct 工具循环内 await 工具执行），
    # 必须经 partial 传依赖——包一层同步 lambda 会丢掉 coroutine 语义。
    graph.add_node("medication", _timed("medication", partial(medication_node, provider=resolved)))
    graph.add_node("qc", _timed("qc", lambda s: qc_node(s, resolved)))
    graph.add_node("rewrite", _timed("rewrite", rewrite_node))
    graph.add_node(
        "hitl",
        _timed(
            "hitl",
            lambda s: escalate_node(s, resolved, interrupt_enabled=interrupt_enabled),
        ),
    )
    graph.add_node("refuse", _timed("refuse", lambda s: refuse_node(s, resolved)))
    graph.add_node("responder", _timed("responder", lambda s: responder_node(s, resolved)))

    graph.add_edge(START, "scope_check")
    graph.add_edge("scope_check", "router")
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {
            "hitl": "hitl",
            "refuse": "refuse",
            "report": "report_interpreter",
            "memory_recall": "memory_recall",
        },
    )
    graph.add_conditional_edges(
        "memory_recall",
        _route_after_memory,
        {"triage": "triage", "medication": "medication"},
    )
    for node in _QC_UPSTREAM_NODES:
        graph.add_edge(node, "qc")
    graph.add_conditional_edges("qc", _route_after_qc, _QC_ROUTES)
    graph.add_edge("rewrite", "qc")
    graph.add_edge("responder", END)

    compiled = graph.compile(checkpointer=checkpointer)
    return compiled.with_config(recursion_limit=_RECURSION_LIMIT)
