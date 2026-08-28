from __future__ import annotations

from care_lifeline.config import get_settings
from care_lifeline.graph.state import AgentState, ReportResult, last_user_text
from care_lifeline.tools.rag.registry import build_report_retriever
from care_lifeline.tools.report_interpreter import (
    LLMReportInterpreter,
    MockReportInterpreter,
    ReportInterpreter,
)


def report_interpreter_node(state: AgentState, provider) -> dict:
    text = last_user_text(state["messages"])
    mode = get_settings().llm_mode
    interpreter: ReportInterpreter = (
        LLMReportInterpreter(provider) if mode == "real" else MockReportInterpreter()
    )
    bundle = build_report_retriever()
    result = (
        interpreter.interpret(text, bundle[0], bundle[1]) if bundle else interpreter.interpret(text)
    )
    return {"report": result, "citations": result.citations, "draft": _summarize(result)}


def _summarize(result: ReportResult) -> str:
    if not result.fields:
        return "未从文本中解析出结构化指标，建议由医生人工判读报告。"
    lines = []
    for field in result.fields:
        line = f"- {field.name}：{field.value}"
        if field.reference:
            line += f"（参考：{field.reference}）"
        if field.abnormal:
            line += " ⚠️异常"
        lines.append(line)
    return "报告解读：\n" + "\n".join(lines)
