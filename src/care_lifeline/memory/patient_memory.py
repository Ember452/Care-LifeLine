from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import (
    Patient,
    PatientAllergy,
    PatientFollowUp,
    PatientMedication,
    PatientMetric,
)


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


# ---------------------------------------------------------------------------
# 结构化纵向记忆：用药史 / 过敏史 / 随访计划（文档 §7.4）
# ---------------------------------------------------------------------------


def append_medication(
    patient_id: int, name: str, dosage: str | None = None, frequency: str | None = None
) -> PatientMedication:
    """新增一条在用药物记录（默认 active）。"""
    ensure_patient(patient_id)
    maker = get_sessionmaker()
    with maker() as session:
        row = PatientMedication(
            patient_id=patient_id, name=name, dosage=dosage, frequency=frequency
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_medications(patient_id: int, active_only: bool = True) -> list[PatientMedication]:
    """列出用药记录；``active_only`` 只返回在用药物。"""
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(PatientMedication).where(PatientMedication.patient_id == patient_id)
        if active_only:
            stmt = stmt.where(PatientMedication.status == "active")
        return list(session.scalars(stmt.order_by(PatientMedication.id)).all())


def stop_medication(medication_id: int) -> bool:
    """把用药记录标记为 stopped；不存在返回 ``False``。"""
    maker = get_sessionmaker()
    with maker() as session:
        row = session.get(PatientMedication, medication_id)
        if row is None:
            return False
        row.status = "stopped"
        session.commit()
        return True


def append_allergy(
    patient_id: int, allergen: str, reaction: str | None = None, severity: str = "moderate"
) -> PatientAllergy:
    """新增一条过敏记录。"""
    ensure_patient(patient_id)
    maker = get_sessionmaker()
    with maker() as session:
        row = PatientAllergy(
            patient_id=patient_id, allergen=allergen, reaction=reaction, severity=severity
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_allergies(patient_id: int) -> list[PatientAllergy]:
    """列出全部过敏记录。"""
    maker = get_sessionmaker()
    with maker() as session:
        return list(
            session.scalars(
                select(PatientAllergy)
                .where(PatientAllergy.patient_id == patient_id)
                .order_by(PatientAllergy.id)
            ).all()
        )


def add_followup(patient_id: int, plan: str, due_date: datetime | None = None) -> PatientFollowUp:
    """新增一条随访计划（默认 pending）。"""
    ensure_patient(patient_id)
    maker = get_sessionmaker()
    with maker() as session:
        row = PatientFollowUp(patient_id=patient_id, plan=plan, due_date=due_date)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_followups(patient_id: int, pending_only: bool = True) -> list[PatientFollowUp]:
    """列出随访计划；``pending_only`` 只返回未完成项。"""
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(PatientFollowUp).where(PatientFollowUp.patient_id == patient_id)
        if pending_only:
            stmt = stmt.where(PatientFollowUp.status == "pending")
        return list(session.scalars(stmt.order_by(PatientFollowUp.id)).all())


def complete_followup(followup_id: int) -> bool:
    """把随访计划标记为 done；不存在返回 ``False``。"""
    maker = get_sessionmaker()
    with maker() as session:
        row = session.get(PatientFollowUp, followup_id)
        if row is None:
            return False
        row.status = "done"
        session.commit()
        return True


def structured_summary(patient_id: int) -> str:
    """把用药/过敏/随访拼成注入分诊上下文的摘要文本；全空返回空串。

    只含结构化脱敏字段（不含自由文本长期留存），符合文档 §7.4 隐私边界。
    """
    sections: list[str] = []
    meds = list_medications(patient_id, active_only=True)
    if meds:
        parts = [
            f"{m.name}" + (f"（{m.dosage}，{m.frequency}）" if m.dosage or m.frequency else "")
            for m in meds
        ]
        sections.append("正在用药：" + "、".join(parts))
    allergies = list_allergies(patient_id)
    if allergies:
        parts = [
            f"{a.allergen}（{a.severity}）" + (f"：{a.reaction}" if a.reaction else "")
            for a in allergies
        ]
        sections.append("过敏史：" + "、".join(parts))
    followups = list_followups(patient_id, pending_only=True)
    if followups:
        parts = [
            f.plan + (f"（截止 {f.due_date:%Y-%m-%d}）" if f.due_date else "")
            for f in followups
        ]
        sections.append("待办随访：" + "、".join(parts))
    return "；".join(sections)
