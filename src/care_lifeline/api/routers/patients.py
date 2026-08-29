from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import (
    PatientMetric,
)
from care_lifeline.memory import patient_memory
from care_lifeline.proactive import scheduler, trigger

router = APIRouter(prefix="/v1/patients", tags=["patients"])


class MetricRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    value: float
    unit: str | None = None
    measured_at: datetime | None = None


class CreatePatientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    age: int | None = Field(default=None, ge=0, le=150)
    gender: str | None = Field(default=None, max_length=16)


class PatientItem(BaseModel):
    id: int
    name: str | None
    age: int | None = None
    gender: str | None = None


class MetricItem(BaseModel):
    id: int
    name: str
    value: float
    unit: str | None
    measured_at: str


class TrendResult(BaseModel):
    name: str
    points: list[dict]


@router.get("", response_model=list[PatientItem])
def list_patients(user: CurrentUser = Depends(get_current_user)) -> list[PatientItem]:
    """患者列表（契约 §7.4）。"""
    return [PatientItem(id=p.id, name=p.name) for p in patient_memory.list_patients()]


@router.post("", response_model=PatientItem)
def create_patient(
    body: CreatePatientRequest, user: CurrentUser = Depends(get_current_user)
) -> PatientItem:
    """新建患者（契约 §7.4，修 P2-10 外键悬空）。"""
    patient = patient_memory.create_patient(body.name)
    return PatientItem(id=patient.id, name=patient.name, age=body.age, gender=body.gender)


@router.post("/{patient_id}/metrics", response_model=dict)
def add_metric(
    patient_id: int, body: MetricRequest, user: CurrentUser = Depends(get_current_user)
) -> dict:
    metric = patient_memory.append_metric(
        patient_id, body.name, body.value, body.unit, body.measured_at
    )
    return {
        "id": metric.id,
        "name": metric.name,
        "value": metric.value,
        "unit": metric.unit,
        "measured_at": str(metric.measured_at),
    }


@router.get("/{patient_id}/metrics", response_model=list[MetricItem])
def metric_history(
    patient_id: int,
    name: Annotated[str, Query(min_length=1)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    user: CurrentUser = Depends(get_current_user),
) -> list[MetricItem]:
    """指标历史（契约 §7.4），支持按名称过滤与条数限制。"""
    trend = patient_memory.get_trend(patient_id, name) if name else _all_metrics(patient_id)
    return [
        MetricItem(
            id=m.id,
            name=m.name,
            value=m.value,
            unit=m.unit,
            measured_at=str(m.measured_at),
        )
        for m in trend[-limit:]
    ]


@router.get("/{patient_id}/trend", response_model=TrendResult)
def metric_trend(
    patient_id: int,
    name: Annotated[str, Query(min_length=1)],
    days: Annotated[int, Query(ge=1, le=365)] = 90,
    user: CurrentUser = Depends(get_current_user),
) -> TrendResult:
    """慢病趋势折线数据（契约 §7.4 图表用）。"""
    trend = patient_memory.get_trend(patient_id, name)
    cutoff = datetime.now().replace(tzinfo=None) - timedelta(days=days)
    points = [
        {"t": m.measured_at.isoformat(), "v": m.value}
        for m in trend
        if m.measured_at is not None and m.measured_at.replace(tzinfo=None) >= cutoff
    ]
    return TrendResult(name=name, points=points)


@router.get("/{patient_id}/reminders", response_model=list[dict])
def reminders(patient_id: int, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    cached = scheduler.get_latest_reminders(patient_id)
    reminders = cached if cached else trigger.evaluate(patient_id)
    return [r.model_dump() for r in reminders]


def _all_metrics(patient_id: int) -> list:
    """取患者全部指标（按名称内排序）。"""
    maker = get_sessionmaker()
    with maker() as session:
        stmt = (
            select(PatientMetric)
            .where(PatientMetric.patient_id == patient_id)
            .order_by(PatientMetric.name, PatientMetric.measured_at)
        )
        return list(session.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# 结构化纵向记忆：用药史 / 过敏史 / 随访计划（文档 §7.4）
# ---------------------------------------------------------------------------


class MedicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    dosage: str | None = Field(default=None, max_length=64)
    frequency: str | None = Field(default=None, max_length=64)
    # 溯源：user 患者自述 | clinician 医生录入 | extracted 会话抽取
    provenance: str = Field(default="user", pattern="^(user|clinician|extracted)$")
    source_session_id: int | None = None


class AllergyCreate(BaseModel):
    allergen: str = Field(min_length=1, max_length=64)
    reaction: str | None = Field(default=None, max_length=128)
    severity: str = Field(default="moderate", pattern="^(mild|moderate|severe)$")
    provenance: str = Field(default="user", pattern="^(user|clinician|extracted)$")
    source_session_id: int | None = None


class FollowUpCreate(BaseModel):
    plan: str = Field(min_length=1, max_length=255)
    due_date: datetime | None = None
    provenance: str = Field(default="user", pattern="^(user|clinician|extracted)$")
    source_session_id: int | None = None


@router.post("/{patient_id}/medications", response_model=dict)
def add_medication(
    patient_id: int, body: MedicationCreate, user: CurrentUser = Depends(get_current_user)
) -> dict:
    row = patient_memory.append_medication(
        patient_id,
        body.name,
        body.dosage,
        body.frequency,
        provenance=body.provenance,
        source_session_id=body.source_session_id,
    )
    return {
        "id": row.id,
        "name": row.name,
        "dosage": row.dosage,
        "frequency": row.frequency,
        "valid_to": str(row.valid_to) if row.valid_to else None,
        "provenance": row.provenance,
    }


@router.get("/{patient_id}/medications", response_model=list[dict])
def medication_list(
    patient_id: int,
    include_history: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """用药列表；``include_history`` 连同已停用（失效）切片一起返回。"""
    return [
        {
            "id": m.id,
            "name": m.name,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "valid_from": str(m.valid_from),
            "valid_to": str(m.valid_to) if m.valid_to else None,
            "provenance": m.provenance,
        }
        for m in patient_memory.list_medications(
            patient_id, active_only=not include_history, include_history=include_history
        )
    ]


@router.delete("/{patient_id}/medications/{medication_id}", response_model=dict)
def stop_medication(
    patient_id: int, medication_id: int, user: CurrentUser = Depends(get_current_user)
) -> dict:
    """停药：关闭 valid_to（失效不删行），历史保留可追溯。"""
    return {"ok": patient_memory.stop_medication(medication_id)}


@router.post("/{patient_id}/allergies", response_model=dict)
def add_allergy(
    patient_id: int, body: AllergyCreate, user: CurrentUser = Depends(get_current_user)
) -> dict:
    row = patient_memory.append_allergy(
        patient_id,
        body.allergen,
        body.reaction,
        body.severity,
        provenance=body.provenance,
        source_session_id=body.source_session_id,
    )
    return {
        "id": row.id,
        "allergen": row.allergen,
        "reaction": row.reaction,
        "severity": row.severity,
        "provenance": row.provenance,
    }


@router.get("/{patient_id}/allergies", response_model=list[dict])
def allergy_list(
    patient_id: int,
    include_history: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return [
        {
            "id": a.id,
            "allergen": a.allergen,
            "reaction": a.reaction,
            "severity": a.severity,
            "provenance": a.provenance,
            "valid_to": str(a.valid_to) if a.valid_to else None,
        }
        for a in patient_memory.list_allergies(patient_id, active_only=not include_history)
    ]


@router.delete("/{patient_id}/allergies/{allergy_id}", response_model=dict)
def deactivate_allergy(
    patient_id: int, allergy_id: int, user: CurrentUser = Depends(get_current_user)
) -> dict:
    """过敏记录失效（误报/已脱敏）：关闭 valid_to，历史保留。"""
    return {"ok": patient_memory.deactivate_allergy(allergy_id)}


@router.post("/{patient_id}/followups", response_model=dict)
def add_followup(
    patient_id: int, body: FollowUpCreate, user: CurrentUser = Depends(get_current_user)
) -> dict:
    row = patient_memory.add_followup(
        patient_id,
        body.plan,
        body.due_date,
        provenance=body.provenance,
        source_session_id=body.source_session_id,
    )
    return {
        "id": row.id,
        "plan": row.plan,
        "due_date": str(row.due_date) if row.due_date else None,
        "status": row.status,
    }


@router.get("/{patient_id}/followups", response_model=list[dict])
def followup_list(patient_id: int, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [
        {
            "id": f.id,
            "plan": f.plan,
            "due_date": str(f.due_date) if f.due_date else None,
            "status": f.status,
        }
        for f in patient_memory.list_followups(patient_id, pending_only=False)
    ]


@router.post("/{patient_id}/followups/{followup_id}/complete", response_model=dict)
def complete_followup(
    patient_id: int, followup_id: int, user: CurrentUser = Depends(get_current_user)
) -> dict:
    return {"ok": patient_memory.complete_followup(followup_id)}


# ---------------------------------------------------------------------------
# 记忆提议-确认流（ADR-0019）：会话抽取的候选变更，写入必须经人工确认
# ---------------------------------------------------------------------------


@router.get("/{patient_id}/memory-proposals", response_model=list[dict])
def proposal_list(
    patient_id: int,
    pending_only: bool = True,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """记忆提议列表（默认待确认）；含对话原句依据与溯源。"""
    return [
        {
            "id": p.id,
            "kind": p.kind,
            "action": p.action,
            "payload": p.payload,
            "excerpt": p.excerpt,
            "thread_id": p.thread_id,
            "status": p.status,
            "decided_by": p.decided_by,
        }
        for p in patient_memory.list_proposals(patient_id, pending_only=pending_only)
    ]


@router.post("/{patient_id}/memory-proposals/{proposal_id}/confirm", response_model=dict)
def confirm_proposal(
    patient_id: int,
    proposal_id: int,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """确认提议：以 provenance=extracted 写入正式记忆表并写审计。"""
    try:
        return patient_memory.confirm_proposal(proposal_id, user.username)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc


@router.post("/{patient_id}/memory-proposals/{proposal_id}/reject", response_model=dict)
def reject_proposal(
    patient_id: int,
    proposal_id: int,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """驳回提议：仅记录决策，不写任何记忆。"""
    try:
        return patient_memory.reject_proposal(proposal_id, user.username)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
