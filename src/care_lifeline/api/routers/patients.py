from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.memory import patient_memory
from care_lifeline.proactive import scheduler, trigger

router = APIRouter(prefix="/v1/patients", tags=["patients"])


class MetricRequest(BaseModel):
    name: str
    value: float
    unit: str | None = None


@router.post("/{patient_id}/metrics", response_model=dict)
def add_metric(
    patient_id: int, body: MetricRequest, user: CurrentUser = Depends(get_current_user)
) -> dict:
    metric = patient_memory.append_metric(patient_id, body.name, body.value, body.unit)
    return {"id": metric.id, "name": metric.name, "value": metric.value, "unit": metric.unit}


@router.get("/{patient_id}/reminders", response_model=list[dict])
def reminders(patient_id: int, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    cached = scheduler.get_latest_reminders(patient_id)
    reminders = cached if cached else trigger.evaluate(patient_id)
    return [r.model_dump() for r in reminders]
