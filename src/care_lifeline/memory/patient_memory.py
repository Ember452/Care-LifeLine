from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import Patient, PatientMetric


def ensure_patient(patient_id: int, name: str | None = None) -> Patient:
    """确保患者行存在（修 P2-10：避免 patient_metrics 外键悬空）。

    Args:
        patient_id: 患者主键。
        name: 患者名；仅在新建患者行时使用。

    Returns:
        已存在或新建的患者行。
    """
    maker = get_sessionmaker()
    with maker() as session:
        patient = session.get(Patient, patient_id)
        if patient is not None:
            return patient
        patient = Patient(id=patient_id, name=name or f"患者{patient_id}")
        session.add(patient)
        session.commit()
        session.refresh(patient)
        return patient


def create_patient(name: str, age: int | None = None, gender: str | None = None) -> Patient:
    """新建患者并返回，供 ``POST /v1/patients`` 使用。

    Note:
        ``age`` / ``gender`` 暂不入库（schema 无对应列），仅做入参校验，
        避免为展示性字段改动数据模型。
    """
    maker = get_sessionmaker()
    with maker() as session:
        patient = Patient(name=name)
        session.add(patient)
        session.commit()
        session.refresh(patient)
        return patient


def list_patients() -> list[Patient]:
    """返回全部患者（按 id 升序）。"""
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(Patient).order_by(Patient.id)
        return list(session.execute(stmt).scalars().all())


def append_metric(
    patient_id: int,
    name: str,
    value: float,
    unit: str | None = None,
    measured_at: datetime | None = None,
) -> PatientMetric:
    ensure_patient(patient_id)
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


def metric_snapshot(patient_id: int) -> dict[str, tuple[float, str | None, float | None]]:
    """返回各指标最新值快照 ``{指标名: (最新值, 单位, 较前值变化)}``。

    单次查询取全量时序后在内存聚合（避免逐指标 N+1）；该患者无任何
    指标时返回空 dict。供纵向记忆节点（P1-F）生成摘要使用。
    """
    maker = get_sessionmaker()
    with maker() as session:
        rows = list(
            session.execute(
                select(PatientMetric)
                .where(PatientMetric.patient_id == patient_id)
                .order_by(PatientMetric.measured_at, PatientMetric.id)
            ).scalars()
        )
    latest: dict[str, PatientMetric] = {}
    previous: dict[str, PatientMetric | None] = {}
    for row in rows:
        previous[row.name] = latest.get(row.name)
        latest[row.name] = row
    snapshot: dict[str, tuple[float, str | None, float | None]] = {}
    for name, row in latest.items():
        prior = previous[name]
        delta = row.value - prior.value if prior is not None else None
        snapshot[name] = (row.value, row.unit, delta)
    return snapshot


def latest_value(patient_id: int, name: str) -> float | None:
    trend = get_trend(patient_id, name)
    return trend[-1].value if trend else None


def list_patient_ids() -> list[int]:
    """Return all distinct patient ids that have at least one recorded metric."""
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(PatientMetric.patient_id).distinct()
        return list(session.execute(stmt).scalars().all())
