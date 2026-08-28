from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.tools.medication import DrugInteraction, MedicationAgent

router = APIRouter(prefix="/v1/medication", tags=["medication"])


class InteractionRequest(BaseModel):
    drugs: list[str]


class TextRequest(BaseModel):
    text: str


@router.post("/interactions", response_model=list[DrugInteraction])
def interactions(
    body: InteractionRequest, user: CurrentUser = Depends(get_current_user)
) -> list[DrugInteraction]:
    return MedicationAgent().check_interactions(body.drugs)


@router.post("/check", response_model=list[DrugInteraction])
def check(
    body: TextRequest, user: CurrentUser = Depends(get_current_user)
) -> list[DrugInteraction]:
    agent = MedicationAgent()
    return agent.check_interactions(agent.extract_drugs(body.text))
