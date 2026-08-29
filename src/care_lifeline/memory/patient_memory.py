from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import (
    MemoryProposal,
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
    patient_id: int,
    name: str,
    dosage: str | None = None,
    frequency: str | None = None,
    provenance: str = "user",
    source_session_id: int | None = None,
) -> PatientMedication:
    """新增一条用药记录（双时间轴：valid_from=now，valid_to=NULL 表示当前有效）。

    Args:
        provenance: 溯源（user 患者自述 | clinician 医生录入 | extracted 会话抽取）。
        source_session_id: 记忆来源会话（管理界面溯源展示用）。
    """
    ensure_patient(patient_id)
    maker = get_sessionmaker()
    with maker() as session:
        row = PatientMedication(
            patient_id=patient_id,
            name=name,
            dosage=dosage,
            frequency=frequency,
            provenance=provenance,
            source_session_id=source_session_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_medications(
    patient_id: int, active_only: bool = True, include_history: bool = False
) -> list[PatientMedication]:
    """列出用药记录。

    Args:
        active_only: 只返回当前有效（``valid_to IS NULL``）的记录；
        include_history: 连同已失效的历史切片一起返回（管理界面/追溯用）。
    """
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(PatientMedication).where(PatientMedication.patient_id == patient_id)
        if active_only and not include_history:
            stmt = stmt.where(PatientMedication.valid_to.is_(None))
        return list(session.scalars(stmt.order_by(PatientMedication.id)).all())


def stop_medication(medication_id: int) -> bool:
    """停药：关闭 ``valid_to``（失效不删行，历史保留可追溯）；不存在或已失效返回 ``False``。"""
    maker = get_sessionmaker()
    with maker() as session:
        row = session.get(PatientMedication, medication_id)
        if row is None or row.valid_to is not None:
            return False
        row.valid_to = datetime.now()
        session.commit()
        return True


def append_allergy(
    patient_id: int,
    allergen: str,
    reaction: str | None = None,
    severity: str = "moderate",
    provenance: str = "user",
    source_session_id: int | None = None,
) -> PatientAllergy:
    """新增一条过敏记录（双时间轴语义同用药史）。"""
    ensure_patient(patient_id)
    maker = get_sessionmaker()
    with maker() as session:
        row = PatientAllergy(
            patient_id=patient_id,
            allergen=allergen,
            reaction=reaction,
            severity=severity,
            provenance=provenance,
            source_session_id=source_session_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def deactivate_allergy(allergy_id: int) -> bool:
    """过敏记录失效（误报/已脱敏）；不存在或已失效返回 ``False``。"""
    maker = get_sessionmaker()
    with maker() as session:
        row = session.get(PatientAllergy, allergy_id)
        if row is None or row.valid_to is not None:
            return False
        row.valid_to = datetime.now()
        session.commit()
        return True


def list_allergies(patient_id: int, active_only: bool = True) -> list[PatientAllergy]:
    """列出过敏记录；``active_only`` 只返回当前有效。"""
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(PatientAllergy).where(PatientAllergy.patient_id == patient_id)
        if active_only:
            stmt = stmt.where(PatientAllergy.valid_to.is_(None))
        return list(session.scalars(stmt.order_by(PatientAllergy.id)).all())


def add_followup(
    patient_id: int,
    plan: str,
    due_date: datetime | None = None,
    provenance: str = "user",
    source_session_id: int | None = None,
) -> PatientFollowUp:
    """新增一条随访计划（默认 pending）。"""
    ensure_patient(patient_id)
    maker = get_sessionmaker()
    with maker() as session:
        row = PatientFollowUp(
            patient_id=patient_id,
            plan=plan,
            due_date=due_date,
            provenance=provenance,
            source_session_id=source_session_id,
        )
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

    只取**当前有效**切片（``valid_to IS NULL`` / 未完成任务）——失效的历史
    疗程不进分诊上下文，但保留在库中可追溯（ADR-0018 双时间轴）。
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


# ---------------------------------------------------------------------------
# 记忆提议-确认流：会话抽取的候选变更，写入必须经人工确认（ADR-0019）
# ---------------------------------------------------------------------------


def _payload_name(payload: dict) -> str:
    return str(payload.get("name") or payload.get("allergen") or payload.get("plan") or "")


def create_proposal(
    patient_id: int,
    kind: str,
    action: str,
    payload: dict,
    thread_id: str | None = None,
    excerpt: str | None = None,
) -> MemoryProposal | None:
    """落一条待确认记忆提议；同患者同内容的 pending 提议已存在时跳过去重。"""
    ensure_patient(patient_id)
    maker = get_sessionmaker()
    with maker() as session:
        from sqlalchemy import select

        existing = session.scalars(
            select(MemoryProposal).where(
                MemoryProposal.patient_id == patient_id,
                MemoryProposal.kind == kind,
                MemoryProposal.action == action,
                MemoryProposal.status == "pending",
            )
        ).all()
        name = _payload_name(payload)
        for row in existing:
            if _payload_name(row.payload) == name:
                return None
        proposal = MemoryProposal(
            patient_id=patient_id,
            thread_id=thread_id,
            kind=kind,
            action=action,
            payload=payload,
            excerpt=excerpt,
        )
        session.add(proposal)
        session.commit()
        session.refresh(proposal)
        return proposal


def list_proposals(patient_id: int, pending_only: bool = True) -> list[MemoryProposal]:
    """列出记忆提议；``pending_only`` 只返回待确认。"""
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(MemoryProposal).where(MemoryProposal.patient_id == patient_id)
        if pending_only:
            stmt = stmt.where(MemoryProposal.status == "pending")
        return list(session.scalars(stmt.order_by(MemoryProposal.id.desc())).all())


def _apply_proposal(proposal: MemoryProposal) -> str:
    """把已确认的提议应用到正式记忆表，返回应用结果描述。

    一律以 ``provenance="extracted"`` 落库；stop 按药名匹配当前有效记录。
    """
    payload = proposal.payload or {}
    name = _payload_name(payload)
    if proposal.kind == "medication":
        if proposal.action == "stop":
            current = [
                m for m in list_medications(proposal.patient_id, active_only=True)
                if m.name == name
            ]
            if not current:
                return f"未找到在用药物「{name}」，未做变更"
            stop_medication(current[0].id)
            return f"已停用「{name}」"
        append_medication(proposal.patient_id, name, provenance="extracted")
        return f"已记录用药「{name}」"
    if proposal.kind == "allergy":
        append_allergy(proposal.patient_id, name, provenance="extracted")
        return f"已记录过敏「{name}」"
    add_followup(proposal.patient_id, name, provenance="extracted")
    return f"已添加随访「{name}」"


def confirm_proposal(proposal_id: int, decided_by: str) -> dict:
    """确认提议：应用到正式记忆表并写审计；不存在或非 pending 抛 ValueError。"""
    maker = get_sessionmaker()
    with maker() as session:
        proposal = session.get(MemoryProposal, proposal_id)
        if proposal is None or proposal.status != "pending":
            raise ValueError(f"提议 {proposal_id} 不存在或已处理")
        applied = _apply_proposal(proposal)
        proposal.status = "confirmed"
        proposal.decided_by = decided_by
        proposal.decided_at = datetime.now()
        session.commit()
        session.refresh(proposal)

        from care_lifeline.db import session_store

        session_row = (
            session_store.get_session_by_thread_id(proposal.thread_id)
            if proposal.thread_id
            else None
        )
        session_store.write_audit(
            session_row.id if session_row is not None else None,
            "memory_proposal_confirmed",
            f"{decided_by}:{proposal.kind}/{proposal.action}:{applied}",
        )
        return {"id": proposal.id, "status": proposal.status, "applied": applied}


def reject_proposal(proposal_id: int, decided_by: str) -> dict:
    """驳回提议（仅记录决策，不写任何记忆）；不存在或非 pending 抛 ValueError。"""
    maker = get_sessionmaker()
    with maker() as session:
        proposal = session.get(MemoryProposal, proposal_id)
        if proposal is None or proposal.status != "pending":
            raise ValueError(f"提议 {proposal_id} 不存在或已处理")
        proposal.status = "rejected"
        proposal.decided_by = decided_by
        proposal.decided_at = datetime.now()
        session.commit()

        from care_lifeline.db import session_store

        session_row = (
            session_store.get_session_by_thread_id(proposal.thread_id)
            if proposal.thread_id
            else None
        )
        session_store.write_audit(
            session_row.id if session_row is not None else None,
            "memory_proposal_rejected",
            f"{decided_by}:{proposal.kind}/{proposal.action}",
        )
        return {"id": proposal.id, "status": proposal.status}
