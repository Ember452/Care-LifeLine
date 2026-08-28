from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import PatientMetric
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
