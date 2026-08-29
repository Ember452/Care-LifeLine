from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from care_lifeline.api.middleware.phi import detect_phi_leak
from care_lifeline.api.runtime import (
    record_latency_ms,
    record_node_ms,
    record_qc_status,
    record_token_usage,
)
from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.checkpointer import get_checkpointer
from care_lifeline.graph.state import AgentState, ToolTrace
from care_lifeline.llm.provider import TokenUsage, make_provider

logger = logging.getLogger(__name__)

_INTERRUPT_EVENT_KEY = "__interrupt__"
_HITL_INTERRUPT_COPY = (
    "检测到高风险信号，已为您转接人工医疗顾问，请耐心等待医生回复；"
    "若情况紧急请立即拨打急救电话或前往急诊。"
)

# 节点名 → 人类可读说明（agent_step 事件用）。
_NODE_LABELS: dict[str, str] = {
    "scope_check": "请求范围判定",
    "router": "意图路由",
    "memory_recall": "调取患者纵向记忆",
    "triage": "分诊",
    "report_interpreter": "报告解读",
    "medication": "用药审查",
    "qc": "质控",
    "rewrite": "重写",
    "hitl": "转人工",
    "refuse": "拒答",
    "responder": "回复生成",
}

# 工具调用事件里参数预览的最大长度（与前端 SSEToolCall 契约一致）。
_TOOL_ARGS_PREVIEW_CHARS = 40


def _persistence_enabled() -> bool:
    return get_settings().database_url.startswith(("sqlite", "postgresql"))


router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    # 可选患者上下文：提供时图内 memory_recall 节点注入纵向指标摘要（P1-F）。
    patient_id: int | None = None


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionItem(BaseModel):
    session_id: str
    title: str | None


@router.get("/sessions", response_model=list[SessionItem])
def list_user_sessions(user: CurrentUser = Depends(get_current_user)) -> list[SessionItem]:
    sessions = session_store.list_sessions(user_id=user.user_id)
    return [SessionItem(session_id=s.thread_id, title=s.title) for s in sessions]


@router.post("/sessions", response_model=SessionItem)
def create_session(
    body: CreateSessionRequest | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> SessionItem:
    """新建会话（契约 §7.2）。"""
    session = session_store.get_or_create_session(
        _new_thread_id(), user_id=user.user_id, title=body.title if body else None
    )
    return SessionItem(session_id=session.thread_id, title=session.title)


@router.delete("/sessions/{session_id}", response_model=dict)
def delete_session(session_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """删除会话（契约 §7.2）。"""
    if not session_store.delete_session(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "会话不存在"},
        )
    return {"ok": True}


@router.get("/sessions/{session_id}/messages", response_model=list[dict])
def session_messages(session_id: str, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """返回会话消息历史（契约 §7.2）。"""
    session = session_store.get_session_by_thread_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "会话不存在"},
        )
    return [
        {"role": m.role, "content": m.content, "citations": m.citations}
        for m in session_store.get_messages(session.id)
    ]


def _new_thread_id() -> str:
    import uuid

    return f"sess_{uuid.uuid4().hex[:12]}"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _initial_state(message: str, patient_id: int | None = None) -> AgentState:
    return {
        "messages": [HumanMessage(message)],
        "patient_id": patient_id,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
        "scope_result": None,
        "retry_count": 0,
        "memory_context": "",
    }


def _persist(session_id: str, user_id: int, user_message: str, state: AgentState) -> None:
    """把本轮对话落库；落库前做 PHI 泄漏检测并写审计（P1-10）。"""
    session = session_store.get_or_create_session(
        session_id, user_id=user_id, title=user_message[:40]
    )
    session_store.append_message(session.id, "user", user_message)
    assistant = session_store.append_message(
        session.id,
        "assistant",
        state["draft"],
        citations=[c.model_dump() for c in state["citations"]],
    )
    leak = detect_phi_leak(state["draft"])
    if leak is not None:
        session_store.write_audit(session.id, "phi_leak", f"type={leak}")
    session_store.write_audit(session.id, "chat_completed", state["intent"])
    qc = state["qc_result"]
    if qc is not None and qc.status in ("hitl", "refused"):
        from care_lifeline.db.models import QcHit

        session_store.record_qc_hits(
            session.id,
            assistant.id,
            [QcHit(rule_code="qc", severity=qc.status, session_id=session.id)],
        )


def _meta_data(req: ChatRequest, state: AgentState) -> dict:
    scope = state.get("scope_result")
    return {
        "session_id": req.session_id,
        "intent": state.get("intent", ""),
        "risk_level": state.get("risk_level", "routine"),
        "scope_verdict": scope.verdict if scope is not None else None,
    }


def _qc_data(qc) -> dict:
    return {
        "status": qc.status,
        "risk_score": qc.risk_score,
        "violations": qc.violations,
    }


def _tool_call_data(trace: ToolTrace) -> dict:
    """把真实工具轨迹转成前端 ``SSEToolCall`` 契约格式。"""
    preview = json.dumps(trace.args, ensure_ascii=False, default=str)
    return {
        "tool": trace.tool,
        "args_preview": preview[:_TOOL_ARGS_PREVIEW_CHARS],
        "ok": trace.ok,
    }


def _usage_data(usage: TokenUsage | None) -> dict | None:
    """token 用量 → done 事件附加字段；无用量时为 ``None``。"""
    if usage is None:
        return None
    return {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "total": usage.total_tokens,
        "estimated": usage.estimated,
    }


def _create_hitl_review(req: ChatRequest, user: CurrentUser, state: AgentState) -> None:
    if not _persistence_enabled():
        return
    with contextlib.suppress(Exception):
        target = session_store.get_session_by_thread_id(req.session_id)
        qc = state["qc_result"]
        if target is not None and qc is not None:
            session_store.create_hitl_review(
                session_id=target.id,
                thread_id=req.session_id,
                input_text=req.message,
                draft=state["draft"],
                qc_json=json.dumps(
                    _qc_data(qc),
                    ensure_ascii=False,
                ),
                violations_json=json.dumps(qc.violations, ensure_ascii=False),
            )
            session_store.write_audit(target.id, "hitl_review_created", user.username)


def _persist_interrupted(req: ChatRequest, user: CurrentUser) -> None:
    """interrupt 真挂起分支的落库配套（P1-E）。

    图在 hitl 节点暂停时还没有 draft/qc 结论，这里用标准转人工文案兜底，
    保证工作台复核队列、审计与消息流不缺记录。
    """
    from care_lifeline.db.models import QcHit

    session = session_store.get_or_create_session(
        req.session_id, user_id=user.user_id, title=req.message[:40]
    )
    session_store.append_message(session.id, "user", req.message)
    session_store.record_qc_hits(
        session.id, None, [QcHit(rule_code="qc", severity="hitl", session_id=session.id)]
    )
    session_store.create_hitl_review(
        session_id=session.id,
        thread_id=req.session_id,
        input_text=req.message,
        draft=_HITL_INTERRUPT_COPY,
        violations_json=json.dumps(["hitl_interrupt"], ensure_ascii=False),
    )
    session_store.write_audit(session.id, "hitl_review_created", user.username)


async def _stream_interrupt(req: ChatRequest, state: AgentState) -> AsyncIterator[str]:
    """interrupt 真挂起分支：只发明确文案，不吐空 token（契约 §4.1）。"""
    yield _sse("meta", _meta_data(req, state))
    yield _sse("hitl", {"reason": "检测到高危症状，需人工医生复核"})
    for chunk in _HITL_INTERRUPT_COPY.split("，"):
        yield _sse("token", {"text": chunk})
    yield _sse("qc", {"status": "hitl", "risk_score": 0.0, "violations": []})
    yield _sse("done", {"final": _HITL_INTERRUPT_COPY, "citations": []})


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest, user: CurrentUser = Depends(get_current_user)
) -> StreamingResponse:
    if not req.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_request", "message": "消息不能为空"},
        )

    async def generate() -> AsyncIterator[str]:
        # 断线重连间隔（P2-A：SSE 工程细节补齐）。
        yield "retry: 3000\n\n"
        checkpointer = get_checkpointer()
        initial = _initial_state(req.message, req.patient_id)
        # 有 checkpointer 时历史由 checkpoint 提供，避免 DB 前置消息重复注入。
        if checkpointer is None and _persistence_enabled():
            with contextlib.suppress(Exception):
                session = await run_in_threadpool(
                    session_store.get_or_create_session,
                    req.session_id,
                    user.user_id,
                    req.message[:40],
                )
                prior = await run_in_threadpool(session_store.get_prior_messages, session.id)
                if prior:
                    initial["messages"] = prior + initial["messages"]

        graph = build_graph(provider := make_provider(), checkpointer=checkpointer)
        config = {"configurable": {"thread_id": req.session_id}} if checkpointer else None
        start = time.perf_counter()
        final_state: AgentState | None = None
        interrupted = False
        try:
            async for mode, chunk in graph.astream(
                initial, config=config, stream_mode=["updates", "values"]
            ):
                if mode == "updates":
                    for node_name, update in chunk.items():
                        if node_name == _INTERRUPT_EVENT_KEY:
                            interrupted = True
                            continue
                        yield _sse(
                            "agent_step",
                            {
                                "node": node_name,
                                "detail": _NODE_LABELS.get(node_name, ""),
                            },
                        )
                        # 单节点耗时（builder 计时包装器写入）→ 运行时指标。
                        if isinstance(update, dict) and "perf_node_ms" in update:
                            record_node_ms(node_name, float(update["perf_node_ms"]))
                        # tool_call 事件来自节点的真实工具轨迹（不再用静态映射伪造）。
                        if isinstance(update, dict) and update.get("tool_traces"):
                            for trace in update["tool_traces"]:
                                yield _sse("tool_call", _tool_call_data(trace))
                        if isinstance(update, dict) and update.get("memory_context"):
                            yield _sse(
                                "memory",
                                {
                                    "patient_id": initial.get("patient_id"),
                                    "metrics_used": [],
                                },
                            )
                else:
                    final_state = chunk
        except Exception as exc:
            logger.exception("chat_stream_failed", exc_info=exc)
            yield _sse(
                "error",
                {"code": "internal_error", "message": "处理失败，请稍后重试"},
            )
            return

        record_latency_ms((time.perf_counter() - start) * 1000)
        state = final_state if final_state is not None else initial

        # 运行时指标采集：质控结论计数 + 本请求 token 用量（provider 实例级）。
        qc = state["qc_result"]
        if qc is not None:
            record_qc_status(qc.status)
        usage = getattr(provider, "last_usage", None)
        if usage is not None:
            record_token_usage(req.session_id, usage)

        if interrupted:
            if _persistence_enabled():
                with contextlib.suppress(Exception):
                    await run_in_threadpool(_persist_interrupted, req, user)
            async for chunk in _stream_interrupt(req, state):
                yield chunk
            return

        if _persistence_enabled():
            with contextlib.suppress(Exception):
                await run_in_threadpool(_persist, req.session_id, user.user_id, req.message, state)

        if qc is not None and qc.status == "hitl":
            display = (
                "检测到高风险信号，已为您转接人工医疗顾问；若情况紧急请立即拨打急救电话或前往急诊。"
            )
            yield _sse("meta", _meta_data(req, state))
            yield _sse("hitl", {"reason": qc.violations})
            for chunk in display.split("，"):
                yield _sse("token", {"text": chunk})
            yield _sse("qc", _qc_data(qc))
            yield _sse(
                "done",
                {
                    "final": display,
                    "citations": [],
                    "token_usage": _usage_data(usage),
                },
            )
            _create_hitl_review(req, user, state)
            return

        if qc is not None and qc.status == "refused":
            display = "抱歉，该问题超出本助手服务范围，建议咨询具备资质的医生获取专业意见。"
            yield _sse("meta", _meta_data(req, state))
            yield _sse("token", {"text": display})
            yield _sse("qc", _qc_data(qc))
            yield _sse(
                "done",
                {
                    "final": display,
                    "citations": [],
                    "token_usage": _usage_data(usage),
                },
            )
            return

        yield _sse("meta", _meta_data(req, state))
        for chunk in state["draft"].split("，"):
            yield _sse("token", {"text": chunk})
        for citation in state["citations"]:
            yield _sse(
                "citation",
                {
                    "index": citation.index,
                    "source": citation.source,
                    "snippet": citation.snippet,
                },
            )
        default_qc = {"status": "passed", "risk_score": 0.0, "violations": []}
        yield _sse("qc", _qc_data(qc) if qc is not None else default_qc)
        yield _sse(
            "done",
            {
                "final": state["draft"],
                "citations": [c.model_dump() for c in state["citations"]],
                "token_usage": _usage_data(usage),
            },
        )

    # P2-A：禁缓存 + 禁反向代理缓冲，保证 SSE 不被中间层攒批。
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
