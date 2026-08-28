from __future__ import annotations

import asyncio

from care_lifeline.tools.base import ToolResult
from care_lifeline.tools.registry import (
    ALL_TOOLS,
    DrugInteractionTool,
    MetricTrendTool,
    ReportParseTool,
    get_tool,
)


def test_all_tools_has_four_and_get_tool_resolves() -> None:
    names = [tool.name for tool in ALL_TOOLS]
    assert names == ["guideline_search", "report_parse", "drug_interaction", "metric_trend"]
    report_tool = get_tool("report_parse")
    assert report_tool is not None
    assert report_tool.name == "report_parse"
    assert get_tool("nonexistent") is None


def test_report_parse_tool_returns_structured_fields() -> None:
    result = asyncio.run(ReportParseTool().run(text="血压：150/95 mmHg"))
    assert result.ok is True
    fields = result.data["fields"]
    assert any(f["name"] == "血压" for f in fields)


def test_drug_interaction_tool_detects_pair() -> None:
    result = asyncio.run(DrugInteractionTool().run(drugs=["华法林", "阿司匹林"]))
    assert result.ok is True
    interactions = result.data["interactions"]
    assert len(interactions) == 1
    assert interactions[0]["severity"] == "major"


def test_metric_trend_tool_requires_db(monkeypatch, tmp_path) -> None:
    from care_lifeline.config import get_settings
    from care_lifeline.db.engine import init_db, reset_state_for_testing

    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/tools.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    from care_lifeline.memory import patient_memory

    patient_memory.append_metric(1, "收缩压", 150.0, "mmHg")
    result = asyncio.run(MetricTrendTool().run(patient_id=1, name="收缩压"))
    assert result.ok is True
    assert result.data["points"][0]["v"] == 150.0
    reset_state_for_testing()


def test_tool_result_defaults() -> None:
    result = ToolResult(ok=True, data={"x": 1})
    assert result.citations == []
    assert result.error is None
    assert isinstance(result, ToolResult)
