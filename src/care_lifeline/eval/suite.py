from __future__ import annotations

import asyncio
import json
import os

from langchain_core.messages import HumanMessage

from care_lifeline.eval.metrics import compute_metrics
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.tools.report_interpreter import MockReportInterpreter

DATA_DIR = os.path.join("data", "eval")


def _load(name: str) -> list[dict]:
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _initial(text: str) -> AgentState:
    return {
        "messages": [HumanMessage(text)],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
        "report": None,
    }


def _run_graph(text: str) -> dict:
    state = asyncio.run(build_graph(MockProvider()).ainvoke(_initial(text)))
    qc = state["qc_result"]
    status = qc.status if qc is not None else "passed"
    draft = state["draft"]
    return {
        "blocked": status in ("refused", "hitl"),
        "hitl": status == "hitl",
        "has_disclaimer": "免责" in draft,
        "has_citation": ("[" in draft) or ("参考" in draft) or ("引用" in draft),
        "latency_ms": 0,
    }


def run_suite(report_path: str = "eval_report.md") -> dict:
    """Run the eval datasets through the mock stack and emit a Markdown report.

    Datasets (redteam / refusal / report_cases) live under data/eval and are
    NOT used for RAG retrieval, so they never leak into prompt context.
    """
    results: list[dict] = []
    for ds in ("redteam", "refusal"):
        for case in _load(ds):
            row = _run_graph(case["input"])
            row["category"] = ds
            row["expect"] = "refuse"
            results.append(row)

    interpreter = MockReportInterpreter()
    for case in _load("report_cases"):
        parsed = interpreter.interpret(case["text"])
        results.append(
            {
                "category": "report",
                "expect": "answer",
                "blocked": False,
                "hitl": False,
                "has_disclaimer": False,
                "has_citation": bool(parsed.citations),
                "latency_ms": 0,
            }
        )

    metrics = compute_metrics(results)
    report = render_markdown(results, metrics)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    return {"results": results, "metrics": metrics, "report": report, "report_path": report_path}


def render_markdown(results: list[dict], metrics: dict) -> str:
    blocked = sum(1 for r in results if r["blocked"])
    lines = [
        "# Care-LifeLine 评测报告",
        "",
        f"- 用例总数：{len(results)}",
        f"- 被拒答/转人工：{blocked}",
        "",
        "## 指标（设计文档 §9.1）",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 拒答率 refusal_rate | {metrics['refusal_rate']} |",
        f"| 安全率 safety_rate | {metrics['safety_rate']} |",
        f"| 转人工率 hitl_rate | {metrics['hitl_rate']} |",
        f"| 合规率 compliance | {metrics['compliance']} |",
        f"| 忠实率 faithfulness | {metrics['faithfulness']} |",
        f"| 延迟 P95(ms) | {metrics['p95_ms']} |",
        "",
        "## 明细",
        "",
        "| 类别 | 期望 | 拒答/转人工 | 引用 |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['category']} | {r['expect']} | {'是' if r['blocked'] else '否'} | "
            f"{'是' if r['has_citation'] else '否'} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    outcome = run_suite()
    print(f"评测完成 -> {outcome['report_path']}")
    for key, value in outcome["metrics"].items():
        print(f"  {key}: {value}")
