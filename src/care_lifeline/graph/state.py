from typing import Annotated, Any, NotRequired, TypedDict

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


class ToolTrace(BaseModel):
    """单次工具调用的真实轨迹（驱动 SSE ``tool_call`` 事件，替代静态映射）。"""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None
    latency_ms: float = 0.0
    summary: str = ""  # 结果预览（截断，避免完整工具输出进入 checkpoint / SSE）


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
    tool_traces: NotRequired[list[ToolTrace]]  # 工具智能体的真实调用轨迹
    perf_node_ms: NotRequired[float]  # builder 计时包装器写入的节点耗时，指标层消费


def last_user_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""
