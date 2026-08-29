from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel

from care_lifeline.config import get_settings
from care_lifeline.memory import patient_memory

_THRESHOLDS: dict[str, float] = {
    "收缩压": 140.0,
    "舒张压": 90.0,
    "空腹血糖": 7.0,
    "糖化血红蛋白": 6.5,
}


def memory_staleness_reminders(patient_id: int) -> list[Reminder]:
    """记忆保鲜（ADR-0018）：超龄未复核的在用药物/过敏记录生成复核提醒。

    医疗记忆会过期：半年前录入的「在用华法林」可能早已停用。这里不自动
    改写记忆，只提醒患者/医生复核——记忆变更仍走人工确认。
    """
    review_days = get_settings().memory_review_days
    if review_days <= 0:
        return []
    cutoff = datetime.now() - timedelta(days=review_days)
    reminders: list[Reminder] = []
    for med in patient_memory.list_medications(patient_id, active_only=True):
        if med.valid_from is not None and med.valid_from.replace(tzinfo=None) < cutoff:
            reminders.append(
                Reminder(
                    patient_id=patient_id,
                    metric=f"用药:{med.name}",
                    message=(
                        f"「{med.name}」已记录超过 {review_days} 天，"
                        "请确认目前仍在服用；如已停用请更新用药记录。"
                    ),
                    severity="info",
                )
            )
    for allergy in patient_memory.list_allergies(patient_id, active_only=True):
        if allergy.valid_from is not None and allergy.valid_from.replace(tzinfo=None) < cutoff:
            reminders.append(
                Reminder(
                    patient_id=patient_id,
                    metric=f"过敏:{allergy.allergen}",
                    message=(
                        f"过敏记录「{allergy.allergen}」已超过 {review_days} 天未复核，"
                        "请确认是否仍然有效。"
                    ),
                    severity="info",
                )
            )
    return reminders


class Reminder(BaseModel):
    patient_id: int
    metric: str
    message: str
    severity: str = "info"


def evaluate(patient_id: int) -> list[Reminder]:
    """Minimal Proactive rule: flag the latest metric above its clinical threshold."""
    reminders: list[Reminder] = []
    for metric_name, threshold in _THRESHOLDS.items():
        value = patient_memory.latest_value(patient_id, metric_name)
        if value is not None and value > threshold:
            reminders.append(
                Reminder(
                    patient_id=patient_id,
                    metric=metric_name,
                    message=f"{metric_name}最新 {value} 超过目标 {threshold}，建议复诊评估。",
                    severity="warning",
                )
            )
    return reminders
