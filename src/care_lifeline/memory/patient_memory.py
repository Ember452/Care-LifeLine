from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import PatientMetric


def append_metric(
    patient_id: int,
    name: str,
    value: float,
    unit: str | None = None,
    measured_at: datetime | None = None,
) -> PatientMetric:
    maker = get_sessionmaker()
    with maker() as session:
        metric = PatientMetric(
            patient_id=patient_id,
            name=name,
            value=value,
            unit=unit,
            measured_at=measured_at or datetime.now(),
        )
        session.add(metric)
        session.commit()
        session.refresh(metric)
        return metric


def get_trend(patient_id: int, name: str) -> list[PatientMetric]:
    maker = get_sessionmaker()
    with maker() as session:
        stmt = (
            select(PatientMetric)
            .where(PatientMetric.patient_id == patient_id, PatientMetric.name == name)
            .order_by(PatientMetric.measured_at)
        )
        return list(session.execute(stmt).scalars().all())


def latest_value(patient_id: int, name: str) -> float | None:
    trend = get_trend(patient_id, name)
    return trend[-1].value if trend else None
