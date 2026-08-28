from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.types import Command
from pydantic import BaseModel, Field

from care_lifeline.api.security import (
    ROLE_ADMIN,
    ROLE_CLINICIAN,
    CurrentUser,
    require_roles,
)
from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.checkpointer import get_checkpointer
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import make_provider

router = APIRouter(prefix="/v1/hitl", tags=["hitl"])

# /v1/hitl/* 仅 clinician / admin（契约 §6）。
_require_clinician = require_roles(ROLE_CLINICIAN, ROLE_ADMIN)


class ClinicianReply(BaseModel):
    session_id: str
    message: str


class QueueItem(BaseModel):
    session_id: str
    title: str | None


class ResumeRequest(BaseModel):
    """恢复被 interrupt 挂起的 HITL 会话（契约 §7.5）。"""

    session_id: str
    decision: str = Field(pattern="^(approve|reject|edit|revise)$")
    corrected_text: str | None = None


class ResumeResponse(BaseModel):
    ok: bool
    final: str
    citations: list[dict]


@router.post("/reply", response_model=dict)
def clinician_reply(
    body: ClinicianReply, user: Annotated[CurrentUser, Depends(_require_clinician)]
) -> dict:
    session = session_store.get_session_by_thread_id(body.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "会话不存在"},
        )
    session_store.append_clinician_message(session.id, body.message)
    session_store.write_audit(session.id, "clinician_reply", user.username)
    return {"ok": True}


@router.get("/queue", response_model=list[QueueItem], dependencies=[Depends(_require_clinician)])
def hitl_queue() -> list[QueueItem]:
    sessions = session_store.list_hitl_sessions()
    return [QueueItem(session_id=s.thread_id, title=s.title) for s in sessions]


@router.post("/resume", response_model=ResumeResponse)
async def resume(
    body: ResumeRequest, user: Annotated[CurrentUser, Depends(_require_clinician)]
) -> ResumeResponse:
    """用 ``Command(resume=...)`` 恢复被 interrupt 挂起的会话（契约 §4.1 / §7.5）。

    无 checkpointer（SQLite 等）时降级为软 HITL：直接把医生修正文本写入会话，
    不抛错、不阻塞。
    """
    checkpointer = get_checkpointer()
    if checkpointer is None:
        session = session_store.get_session_by_thread_id(body.session_id)
        if session is not None and body.corrected_text:
            session_store.append_clinician_message(session.id, body.corrected_text)
        session_store.write_audit(
            session.id if session is not None else None,
            f"hitl_resume_{body.decision}",
            f"{user.username}:degraded_no_checkpointer",
        )
        return ResumeResponse(ok=True, final=body.corrected_text or "", citations=[])

    graph = build_graph(make_provider(), checkpointer=checkpointer)
    config = {"configurable": {"thread_id": body.session_id}}
    resume_payload = {"corrected_text": body.corrected_text} if body.corrected_text else None
    final_state: AgentState = await graph.ainvoke(Command(resume=resume_payload), config=config)
    draft = final_state.get("draft", "")
    citations = [c.model_dump() for c in final_state.get("citations", [])]
    if get_settings().database_url.startswith(("sqlite", "postgresql")):
        session = session_store.get_session_by_thread_id(body.session_id)
        if session is not None:
            session_store.append_message(session.id, "assistant", draft, citations=citations)
            session_store.write_audit(session.id, f"hitl_resume_{body.decision}", user.username)
    return ResumeResponse(ok=True, final=draft, citations=citations)
