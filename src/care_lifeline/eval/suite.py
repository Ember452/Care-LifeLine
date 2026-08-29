from __future__ import annotations

import asyncio
import json
import os
import time

from langchain_core.messages import HumanMessage

from care_lifeline.eval.metrics import compute_metrics
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.tools.rag.registry import build_report_retriever
from care_lifeline.tools.report_interpreter import (
    MockReportInterpreter,
    citation_has_real_source,
)

DATA_DIR = os.path.join("data", "eval")

# 数据飞轮：workbench 审核沉淀的反馈样本集（P2-17）。
_FEEDBACK_DATASET = "feedback_cases"


def _load(name: str) -> list[dict]:
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return []
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
        "medication_warnings": [],
    }


def _run_graph(text: str, provider=None) -> dict:
    """跑一次图并记录真实端到端延迟（P1-9：不再硬编码 0）。"""
    start = time.perf_counter()
    state = asyncio.run(build_graph(provider or MockProvider()).ainvoke(_initial(text)))
    latency_ms = (time.perf_counter() - start) * 1000
    qc = state["qc_result"]
    status = qc.status if qc is not None else "passed"
    draft = state["draft"]
    return {
        "blocked": status in ("refused", "hitl"),
        "hitl": status == "hitl",
        "has_disclaimer": "免责" in draft,
        # 忠实引用口径收紧：必须含真实 source，而不是「出现了 [ / 参考 / 引用」。
        "has_citation": any(citation_has_real_source(c) for c in state.get("citations", [])),
        "latency_ms": round(latency_ms, 2),
    }


def _run_report(text: str) -> dict:
    """报告解读用例：优先用真实指南语料检索，保证引用含真实 source。"""
    start = time.perf_counter()
    interpreter = MockReportInterpreter()
    bundle = build_report_retriever()
    parsed = (
        interpreter.interpret(text, bundle[0], bundle[1]) if bundle else interpreter.interpret(text)
    )
    latency_ms = (time.perf_counter() - start) * 1000
    return {
        "category": "report",
        "expect": "answer",
        "blocked": False,
        "hitl": False,
        "has_disclaimer": False,
        "has_citation": any(citation_has_real_source(c) for c in parsed.citations),
        "latency_ms": round(latency_ms, 2),
    }


def _feedback_expect(case: dict) -> str:
    """推断反馈样本的正确期望结果。

    reject 表示医生认定该回复应被拦截；approve/edit 中 violations 含
    emergency（或明确标注「已转人工」）的样本，医生认可的就是「转人工」
    这个动作本身——图再次正确转 HITL 才算通过，故期望也是 refuse。
    其余 approve/edit 才期望产出可用回答。
    """
    if case.get("decision") == "reject":
        return "refuse"
    violations = [str(v) for v in case.get("violations", [])]
    if "emergency" in violations or any("转人工" in v for v in violations):
        return "refuse"
    return "answer"


def _run_feedback(case: dict, provider=None) -> dict:
    """数据飞轮回归（P2-17）：把审核沉淀的反馈样本重新过一遍图。"""
    row = _run_graph(case.get("input", ""), provider)
    row["category"] = "feedback"
    row["expect"] = _feedback_expect(case)
    return row


def run_suite(report_path: str = "eval_report.md", provider=None) -> dict:
    """Run the eval datasets through the graph stack and emit a Markdown report.

    Datasets (redteam / refusal / report_cases / feedback_cases) live under
    data/eval and are NOT used for RAG retrieval, so they never leak into
    prompt context. Feedback cases are clinician-approved samples appended by
    the workbench flywheel (P2-17).

    Args:
        report_path: 报告输出路径。
        provider: LLM 提供者；缺省用 MockProvider（``--mode real`` 可切真实模型）。
    """
    resolved = provider or MockProvider()
    results: list[dict] = []
    for ds in ("redteam", "refusal"):
        for case in _load(ds):
            row = _run_graph(case["input"], resolved)
            row["category"] = ds
            row["expect"] = "refuse"
            results.append(row)

    for case in _load("report_cases"):
        results.append(_run_report(case["text"]))

    for case in _load(_FEEDBACK_DATASET):
        results.append(_run_feedback(case, resolved))

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
    import argparse
    import sys

    from care_lifeline.config import get_settings

    parser = argparse.ArgumentParser(description="Care-LifeLine 评测套件")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock", help="评测用 LLM 模式")
    args = parser.parse_args()

    provider = None
    if args.mode == "real":
        settings = get_settings()
        if settings.llm_mode != "real":
            print("错误：--mode real 需要 CARE_LLM_MODE=real（意图/质控的 LLM 判定才生效）")
            sys.exit(2)
        try:
            from care_lifeline.llm.real_provider import RealProvider

            provider = RealProvider(settings)
        except RuntimeError as exc:
            print(f"错误：{exc}")
            sys.exit(2)

    outcome = run_suite(provider=provider)
    print(f"评测完成 -> {outcome['report_path']}")
    for key, value in outcome["metrics"].items():
        print(f"  {key}: {value}")
