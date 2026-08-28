from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.db import session_store

router = APIRouter(prefix="/v1/hitl", tags=["hitl"])


class ClinicianReply(BaseModel):
    session_id: str
    message: str


class QueueItem(BaseModel):
    session_id: str
    title: str | None


@router.post("/reply", response_model=dict)
def clinician_reply(
    body: ClinicianReply, user: CurrentUser = Depends(get_current_user)
) -> dict:
    session = session_store.get_session_by_thread_id(body.session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    session_store.append_clinician_message(session.id, body.message)
    session_store.write_audit(session.id, "clinician_reply", user.username)
    return {"ok": True}


@router.get("/queue", response_model=list[QueueItem])
def hitl_queue(user: CurrentUser = Depends(get_current_user)) -> list[QueueItem]:
    sessions = session_store.list_hitl_sessions()
    return [QueueItem(session_id=s.thread_id, title=s.title) for s in sessions]
