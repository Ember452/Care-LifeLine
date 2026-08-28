from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from care_lifeline.api.security import CurrentUser, get_current_user
from care_lifeline.config import get_settings
from care_lifeline.graph.state import ReportResult
from care_lifeline.llm.provider import make_provider
from care_lifeline.tools.rag.registry import build_report_retriever
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
        LLMReportInterpreter(make_provider()) if mode == "real" else MockReportInterpreter()
    )
    bundle = build_report_retriever()
    if bundle:
        return interpreter.interpret(body.text, bundle[0], bundle[1])
    return interpreter.interpret(body.text)
