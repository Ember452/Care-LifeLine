from __future__ import annotations

from typing import Any

from care_lifeline.graph.state import Citation
from care_lifeline.memory import patient_memory
from care_lifeline.tools.base import CareTool, ToolResult
from care_lifeline.tools.medication import MedicationAgent
from care_lifeline.tools.rag.registry import build_report_retriever
from care_lifeline.tools.report_interpreter import MockReportInterpreter


class GuidelineSearchTool(CareTool):
    """指南检索工具：包装 ``build_report_retriever()``。"""

    name = "guideline_search"
    description = "检索中文临床指南语料，返回与问题最相关的指南片段。"

    async def run(self, query: str, k: int = 3, **kwargs: Any) -> ToolResult:  # type: ignore[override]
        bundle = build_report_retriever()
        if bundle is None:
            return ToolResult(ok=False, data={}, error="指南语料不可用")
        retriever, reranker, _chunks = bundle
        chunks = reranker.rerank(query, retriever.retrieve(query, k=k))
        return ToolResult(
            ok=True,
            data={"chunks": [c.model_dump() for c in chunks]},
            citations=[
                Citation(index=i, source=chunk.source or "指南", snippet=chunk.text[:80])
                for i, chunk in enumerate(chunks)
            ],
        )


class ReportParseTool(CareTool):
    """报告解析工具：包装 ``ReportInterpreter``。"""

    name = "report_parse"
    description = "把自由文本的检验/体检报告解析为结构化指标字段。"

    async def run(self, text: str, **kwargs: Any) -> ToolResult:  # type: ignore[override]
        interpreter = MockReportInterpreter()
        result = interpreter.interpret(text)
        return ToolResult(
            ok=True,
            data={"fields": [f.model_dump() for f in result.fields]},
            citations=list(result.citations),
        )


class DrugInteractionTool(CareTool):
    """用药相互作用工具：包装 ``MedicationAgent``。"""

    name = "drug_interaction"
    description = "检查多药联用的相互作用风险（离线 DDI 知识库）。"

    async def run(self, drugs: list[str] | str, **kwargs: Any) -> ToolResult:  # type: ignore[override]
        agent = MedicationAgent()
        names = agent.extract_drugs(drugs) if isinstance(drugs, str) else drugs
        hits = agent.check_interactions(names)
        return ToolResult(
            ok=True,
            data={"interactions": [hit.model_dump() for hit in hits]},
            citations=[],
        )


class MetricTrendTool(CareTool):
    """患者纵向指标工具：包装 ``patient_memory``。"""

    name = "metric_trend"
    description = "查询患者指定指标的纵向趋势数据（脱敏后指标值）。"

    async def run(self, patient_id: int, name: str, **kwargs: Any) -> ToolResult:  # type: ignore[override]
        trend = patient_memory.get_trend(patient_id, name)
        return ToolResult(
            ok=True,
            data={
                "patient_id": patient_id,
                "points": [{"t": str(m.measured_at), "v": m.value, "unit": m.unit} for m in trend],
            },
            citations=[],
        )


ALL_TOOLS: list[CareTool] = [
    GuidelineSearchTool(),
    ReportParseTool(),
    DrugInteractionTool(),
    MetricTrendTool(),
]


def get_tool(name: str) -> CareTool | None:
    """按名称查找工具；未注册时返回 ``None``。"""
    return next((tool for tool in ALL_TOOLS if tool.name == name), None)
