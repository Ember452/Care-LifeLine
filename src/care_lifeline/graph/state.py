from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class Citation(BaseModel):
    index: int
    source: str
    snippet: str


class QCResult(BaseModel):
    status: str  # passed | hitl | refused
    risk_score: float = 0.0
    violations: list[str] = Field(default_factory=list)


class ReportField(BaseModel):
    name: str
    value: str
    reference: str | None = None
    abnormal: bool = False


class ReportResult(BaseModel):
    fields: list[ReportField] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    patient_id: str | None
    intent: str
    risk_level: str  # routine | urgent | critical
    citations: list[Citation]
    draft: str
    qc_result: QCResult | None
    hitl_required: bool
    report: ReportResult | None
    medication_warnings: list[str]


def last_user_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""
