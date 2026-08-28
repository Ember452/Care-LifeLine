from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.tools.ocr import PillboxResult, PillboxVision

router = APIRouter(prefix="/v1/ocr", tags=["ocr"])


class PillboxResponse(BaseModel):
    items: list[dict]
    note: str


@router.post("/pillbox", response_model=PillboxResponse)
async def pillbox(
    file: UploadFile = File(...), user: CurrentUser = Depends(get_current_user)
) -> PillboxResponse:
    data = await file.read()
    result: PillboxResult = PillboxVision().interpret(data)
    return PillboxResponse(items=result.items, note=result.note)
