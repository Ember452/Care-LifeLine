from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from care_lifeline.api.runtime import (
    node_latency_summary,
    p95_latency_ms,
    qc_status_counts,
    token_summary,
)
from care_lifeline.api.security import ROLE_ADMIN, CurrentUser, require_roles
from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import AuditLog, HitlReview, Message, QcHit, Session
from care_lifeline.safety import rules_engine
from care_lifeline.tools.report_interpreter import citation_has_real_source

router = APIRouter(prefix="/v1/admin", tags=["admin"])

# /v1/admin/* 仅 admin 角色（契约 §6）。
_require_admin = require_roles(ROLE_ADMIN)


class Metrics(BaseModel):
    """管理后台总览指标（契约 §7.6）。"""

    total_sessions: int
    total_messages: int
    refusal_rate: float
    safety_rate: float
    hitl_rate: float
    compliance: float
    faithfulness: float
    p95_ms: float
    leak_rate: float
    pending_reviews: int
    refuse_rate: float  # 兼容旧字段名
    # 运行时可观测性（进程内采样，重启清零）。
    node_latency: dict[str, dict[str, float]]  # 节点 → {count, p50_ms, p95_ms}
    qc_status_counts: dict[str, int]  # 质控结论计数
    token_usage: dict[str, object]  # token 用量汇总（全局 + 会话明细）

    model_config = {"extra": "forbid"}


class RuleToggle(BaseModel):
    code: str
    enabled: bool


class TrendItem(BaseModel):
    dates: list[str]
    sessions: list[int]
    refusals: list[int]
    hitls: list[int]


class AuditItem(BaseModel):
    id: int
    event: str
    session_id: int | None
    detail: str | None
    created_at: str


def _real_source_fraction(citations: list[dict]) -> float:
    """统计带引用消息中「含真实 source」的比例；无引用样本时按 1.0 处理。"""
    if not citations:
        return 1.0
    grounded = sum(1 for c in citations if citation_has_real_source(c))
    return round(grounded / len(citations), 4)


def _token_summary_with_cost() -> dict[str, object]:
    """token 汇总 + 按配置单价折算的估算成本（单价 0 时不含 cost 字段）。"""
    summary = token_summary()
    settings = get_settings()
    if settings.token_price_input_per_1k or settings.token_price_output_per_1k:
        input_tokens = float(summary.get("total_input_tokens", 0.0))  # type: ignore[arg-type]
        output_tokens = float(summary.get("total_output_tokens", 0.0))  # type: ignore[arg-type]
        cost = (
            input_tokens / 1000 * settings.token_price_input_per_1k
            + output_tokens / 1000 * settings.token_price_output_per_1k
        )
        summary["estimated_cost"] = round(cost, 4)
    return summary


def _metrics() -> Metrics:
    maker = get_sessionmaker()
    with maker() as db:
        total = db.execute(select(func.count(Session.id))).scalar() or 0
        total_messages = db.execute(select(func.count(Message.id))).scalar() or 0
        hitl = (
            db.execute(select(func.count(QcHit.id)).where(QcHit.severity == "hitl")).scalar() or 0
        )
        refused = (
            db.execute(select(func.count(QcHit.id)).where(QcHit.severity == "refused")).scalar()
            or 0
        )
        leaks = (
            db.execute(select(func.count(AuditLog.id)).where(AuditLog.event == "phi_leak")).scalar()
            or 0
        )
        pending = (
            db.execute(
                select(func.count(HitlReview.id)).where(HitlReview.status == "pending")
            ).scalar()
            or 0
        )
        assistant_msgs = (
            db.execute(select(Message).where(Message.role == "assistant")).scalars().all()
        )
    citations = [c for msg in assistant_msgs if msg.citations for c in msg.citations]
    base = total or 1
    safe = max(total - hitl - refused, 0)
    refusal_rate = round(refused / base, 4)
    return Metrics(
        total_sessions=total,
        total_messages=total_messages,
        refusal_rate=refusal_rate,
        safety_rate=round(safe / base, 4),
        hitl_rate=round(hitl / base, 4),
        compliance=1.0 if total == 0 else round(safe / base, 4),
        faithfulness=_real_source_fraction(citations),
        p95_ms=p95_latency_ms(),
        leak_rate=round(leaks / base, 4),
        pending_reviews=pending,
        refuse_rate=refusal_rate,
        node_latency=node_latency_summary(),
        qc_status_counts=qc_status_counts(),
        token_usage=_token_summary_with_cost(),
    )


@router.get("/metrics", response_model=Metrics)
def metrics(user: Annotated[CurrentUser, Depends(_require_admin)]) -> Metrics:
    return _metrics()


@router.get("/audit", response_model=list[AuditItem], dependencies=[Depends(_require_admin)])
def audit(
    event: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditItem]:
    """全量审计流（契约 §7.6），支持 event / limit / offset 过滤。"""
    rows = session_store.list_audit_logs(event=event, limit=limit, offset=offset)
    return [
        AuditItem(
            id=row.id,
            event=row.event,
            session_id=row.session_id,
            detail=row.detail,
            created_at=str(row.created_at),
        )
        for row in rows
    ]


@router.get("/audit/sessions/{thread_id}")
def audit_trace(thread_id: str, user: Annotated[CurrentUser, Depends(_require_admin)]) -> dict:
    session = session_store.get_session_by_thread_id(thread_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "会话不存在"},
        )
    messages = [
        {"role": m.role, "content": m.content, "citations": m.citations}
        for m in session_store.get_messages(session.id)
    ]
    maker = get_sessionmaker()
    with maker() as db:
        audit = [
            {"event": a.event, "detail": a.detail, "created_at": str(a.created_at)}
            for a in db.execute(
                select(AuditLog).where(AuditLog.session_id == session.id).order_by(AuditLog.id)
            ).scalars()
        ]
    return {"thread_id": thread_id, "messages": messages, "audit": audit}


@router.get("/rules")
def rules(user: Annotated[CurrentUser, Depends(_require_admin)]) -> list[dict]:
    return rules_engine.list_rules()


@router.put("/rules")
def toggle_rule(body: RuleToggle, user: Annotated[CurrentUser, Depends(_require_admin)]) -> dict:
    """启停质控规则；变更写审计并落库（P0-5 / P1-D）。"""
    if not any(r["code"] == body.code for r in rules_engine.list_rules()):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "规则不存在"},
        )
    rules_engine.set_rule_enabled(body.code, body.enabled)
    session_store.set_qc_rule_enabled(body.code, body.enabled)
    session_store.write_audit(
        None,
        "qc_rule_toggled",
        f"{user.username}:{body.code}={body.enabled}",
    )
    return {"code": body.code, "enabled": body.enabled}


@router.get("/trend", response_model=TrendItem, dependencies=[Depends(_require_admin)])
def trend(
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> TrendItem:
    """运营趋势（契约 §7.6 图表数据）：近 N 天会话/拒答/转人工按日聚合。"""
    dates: list[str] = []
    sessions: list[int] = []
    refusals: list[int] = []
    hitls: list[int] = []
    maker = get_sessionmaker()
    with maker() as db:
        for days_ago in range(days - 1, -1, -1):
            day = date.today() - timedelta(days=days_ago)
            day_start = datetime.combine(day, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            dates.append(day.isoformat())
            sessions.append(
                db.execute(
                    select(func.count(Session.id)).where(
                        Session.created_at >= day_start, Session.created_at < day_end
                    )
                ).scalar()
                or 0
            )
            refusals.append(
                db.execute(
                    select(func.count(QcHit.id)).where(
                        QcHit.severity == "refused",
                        QcHit.created_at >= day_start,
                        QcHit.created_at < day_end,
                    )
                ).scalar()
                or 0
            )
            hitls.append(
                db.execute(
                    select(func.count(QcHit.id)).where(
                        QcHit.severity == "hitl",
                        QcHit.created_at >= day_start,
                        QcHit.created_at < day_end,
                    )
                ).scalar()
                or 0
            )
    return TrendItem(dates=dates, sessions=sessions, refusals=refusals, hitls=hitls)
