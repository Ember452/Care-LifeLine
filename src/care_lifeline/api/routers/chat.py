from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.checkpointer import get_checkpointer
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import make_provider


def _persistence_enabled() -> bool:
    return get_settings().database_url.startswith(("sqlite", "postgresql"))

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SessionItem(BaseModel):
    session_id: str
    title: str | None


@router.get("/sessions", response_model=list[SessionItem])
def list_user_sessions(user: CurrentUser = Depends(get_current_user)) -> list[SessionItem]:
    sessions = session_store.list_sessions(user_id=user.user_id)
    return [SessionItem(session_id=s.thread_id, title=s.title) for s in sessions]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _initial_state(message: str) -> AgentState:
    return {
        "messages": [HumanMessage(message)],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
    }


def _persist(session_id: str, user_id: int, user_message: str, state: AgentState) -> None:
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
    session_store.write_audit(session.id, "chat_completed", state["intent"])
    qc = state["qc_result"]
    if qc is not None and qc.status in ("hitl", "refused"):
        from care_lifeline.db.models import QcHit

        session_store.record_qc_hits(
            session.id,
            assistant.id,
            [QcHit(rule_code="qc", severity=qc.status, session_id=session.id)],
        )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest, user: CurrentUser = Depends(get_current_user)
) -> StreamingResponse:
    if not req.message.strip():

        async def error_stream() -> AsyncIterator[str]:
            yield _sse("error", {"code": "INVALID", "message": "消息不能为空"})

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def generate() -> AsyncIterator[str]:
        initial = _initial_state(req.message)
        if _persistence_enabled():
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

        graph = build_graph(make_provider(), checkpointer=get_checkpointer())
        config = (
            {"configurable": {"thread_id": req.session_id}} if get_checkpointer() else None
        )
        state = await graph.ainvoke(initial, config=config)

        if _persistence_enabled():
            with contextlib.suppress(Exception):
                await run_in_threadpool(_persist, req.session_id, user.user_id, req.message, state)

        qc = state["qc_result"]
        if qc is not None and qc.status == "hitl":
            display = (
                "检测到高风险信号，已为您转接人工医疗顾问；"
                "若情况紧急请立即拨打急救电话或前往急诊。"
            )
            yield _sse(
                "meta",
                {
                    "session_id": req.session_id,
                    "intent": state["intent"],
                    "risk_level": state["risk_level"],
                },
            )
            yield _sse("hitl", {"reason": qc.violations})
            for chunk in display.split("，"):
                yield _sse("token", {"text": chunk})
            yield _sse(
                "qc",
                {"status": qc.status, "risk_score": qc.risk_score, "violations": qc.violations},
            )
            yield _sse("done", {"final": display, "citations": []})
            if _persistence_enabled():
                with contextlib.suppress(Exception):
                    target = session_store.get_session_by_thread_id(req.session_id)
                    if target is not None:
                        session_store.create_hitl_review(
                            session_id=target.id,
                            thread_id=req.session_id,
                            input_text=req.message,
                            draft=state["draft"],
                            qc_json=json.dumps(
                                {
                                    "status": qc.status,
                                    "risk_score": qc.risk_score,
                                    "violations": qc.violations,
                                },
                                ensure_ascii=False,
                            ),
                            violations_json=json.dumps(qc.violations, ensure_ascii=False),
                        )
                        session_store.write_audit(target.id, "hitl_review_created", user.username)
            return

        if qc is not None and qc.status == "refused":
            display = "抱歉，该问题超出本助手服务范围，建议咨询具备资质的医生获取专业意见。"
            yield _sse(
                "meta",
                {
                    "session_id": req.session_id,
                    "intent": state["intent"],
                    "risk_level": state["risk_level"],
                },
            )
            yield _sse("token", {"text": display})
            yield _sse(
                "qc",
                {"status": qc.status, "risk_score": qc.risk_score, "violations": qc.violations},
            )
            yield _sse("done", {"final": display, "citations": []})
            return

        yield _sse(
            "meta",
            {
                "session_id": req.session_id,
                "intent": state["intent"],
                "risk_level": state["risk_level"],
            },
        )
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
        yield _sse(
            "qc",
            {
                "status": qc.status,
                "risk_score": qc.risk_score,
                "violations": qc.violations,
            },
        )
        yield _sse(
            "done",
            {
                "final": state["draft"],
                "citations": [c.model_dump() for c in state["citations"]],
            },
        )

    return StreamingResponse(generate(), media_type="text/event-stream")
