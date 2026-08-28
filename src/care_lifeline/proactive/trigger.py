from __future__ import annotations

from pydantic import BaseModel

from care_lifeline.memory import patient_memory

_THRESHOLDS: dict[str, float] = {
    "收缩压": 140.0,
    "舒张压": 90.0,
    "空腹血糖": 7.0,
    "糖化血红蛋白": 6.5,
}


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
