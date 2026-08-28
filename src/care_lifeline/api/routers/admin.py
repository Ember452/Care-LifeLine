from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.db import session_store
from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import AuditLog, QcHit, Session
from care_lifeline.safety import rules_engine

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class Metrics(BaseModel):
    refuse_rate: float
    leak_rate: float
    faithfulness: float
    compliance: float
    hitl_rate: float
    p95_ms: float

    model_config = {"extra": "forbid"}


class RuleToggle(BaseModel):
    code: str
    enabled: bool


def _metrics() -> Metrics:
    maker = get_sessionmaker()
    with maker() as db:
        total = db.execute(select(func.count(Session.id))).scalar() or 0
        hitl = (
            db.execute(
                select(func.count(QcHit.id)).where(QcHit.severity == "hitl")
            ).scalar()
            or 0
        )
        refused = (
            db.execute(
                select(func.count(QcHit.id)).where(QcHit.severity == "refused")
            ).scalar()
            or 0
        )
        leaks = (
            db.execute(
                select(func.count(AuditLog.id)).where(AuditLog.event == "phi_leak")
            ).scalar()
            or 0
        )
    base = total or 1
    safe = max(total - hitl - refused, 0)
    return Metrics(
        refuse_rate=round(refused / base, 4),
        leak_rate=round(leaks / base, 4),
        faithfulness=1.0,
        compliance=1.0 if total == 0 else round(safe / base, 4),
        hitl_rate=round(hitl / base, 4),
        p95_ms=0.0,
    )


@router.get("/metrics", response_model=Metrics)
def metrics(user: CurrentUser = Depends(get_current_user)) -> Metrics:
    return _metrics()


@router.get("/audit/sessions/{thread_id}")
def audit_trace(thread_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    session = session_store.get_session_by_thread_id(thread_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    messages = [
        {"role": m.role, "content": m.content, "citations": m.citations}
        for m in session_store.get_messages(session.id)
    ]
    maker = get_sessionmaker()
    with maker() as db:
        audit = [
            {"event": a.event, "detail": a.detail, "created_at": str(a.created_at)}
            for a in db.execute(
                select(AuditLog)
                .where(AuditLog.session_id == session.id)
                .order_by(AuditLog.id)
            ).scalars()
        ]
    return {"thread_id": thread_id, "messages": messages, "audit": audit}


@router.get("/rules")
def rules(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return rules_engine.list_rules()


@router.put("/rules")
def toggle_rule(body: RuleToggle, user: CurrentUser = Depends(get_current_user)) -> dict:
    if not any(r["code"] == body.code for r in rules_engine.list_rules()):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="规则不存在"
        )
    rules_engine.set_rule_enabled(body.code, body.enabled)
    return {"code": body.code, "enabled": body.enabled}
