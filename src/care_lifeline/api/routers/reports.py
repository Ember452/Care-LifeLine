from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.config import get_settings
from care_lifeline.graph.state import ReportResult
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.tools.report_interpreter import (
    LLMReportInterpreter,
    MockReportInterpreter,
    ReportInterpreter,
)

router = APIRouter(prefix="/v1/report", tags=["report"])


class ReportRequest(BaseModel):
    text: str


@router.post("/interpret", response_model=ReportResult)
def interpret(body: ReportRequest, user: CurrentUser = Depends(get_current_user)) -> ReportResult:
    mode = get_settings().llm_mode
    interpreter: ReportInterpreter = (
        LLMReportInterpreter(MockProvider()) if mode == "real" else MockReportInterpreter()
    )
    return interpreter.interpret(body.text)
