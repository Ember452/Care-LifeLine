from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from care_lifeline.safety.scope import ScopeResult


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
    patient_id: int | None  # 患者 DB 主键；提供时 memory_recall 节点注入纵向记忆
    intent: str  # emergency | medication | report | triage | refuse
    risk_level: str  # routine | urgent | critical
    # 以下三个字段由循环图内部维护，调用方可省略（NotRequired 保证旧调用点不破坏）。
    scope_result: NotRequired[ScopeResult | None]
    citations: list[Citation]
    draft: str
    qc_result: QCResult | None
    hitl_required: bool
    report: ReportResult | None
    medication_warnings: list[str]
    retry_count: NotRequired[int]  # Agent 重写循环计数，上限见 builder._MAX_RETRY
    memory_context: NotRequired[str]  # 患者纵向记忆注入（脱敏后的摘要文本）


def last_user_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""
