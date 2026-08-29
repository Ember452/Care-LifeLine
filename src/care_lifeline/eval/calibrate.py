"""QC 风险阈值校准（设计文档 §9.4）：标注集 + PR 曲线选点。

对 ``data/eval/qc_calibration.json`` 里带 ``pass``/``block`` 标注的草稿，
用 QC LLM 评审员打分，扫描 0.05-0.95 的阈值，输出每个阈值下的
precision/recall/F1 与 F1 最优阈值（并列时取召回更高者——医疗场景
宁可多转人工）。mock 模式下评审员无语义能力，校准仅 real 模式有效。
"""

from __future__ import annotations

from dataclasses import dataclass

from care_lifeline.eval.suite import _load
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.safety.llm_reviewer import LLMReviewer

# 校准扫描的阈值序列（0.05 步长覆盖 0.05-0.95）。
THRESHOLDS: list[float] = [round(0.05 * i, 2) for i in range(1, 20)]

CALIBRATION_REPORT = "eval_calibration.md"


@dataclass(frozen=True)
class ThresholdRow:
    """单个阈值下的混淆指标（正类 = 应转人工 block）。"""

    threshold: float
    precision: float
    recall: float
    f1: float


def collect_scores(cases: list[dict], provider: LLMProvider) -> list[tuple[float, bool]]:
    """用 LLM 评审员给每条标注草稿打分。

    Args:
        cases: ``[{"draft": str, "label": "pass"|"block"}, ...]``。
        provider: real 模式的 LLM 提供者（评审员需要语义打分能力）。

    Returns:
        (risk_score, should_block) 列表；label 非法的用例跳过。
    """
    reviewer = LLMReviewer(provider, threshold=0.0)  # 阈值置 0 只取原始分
    scores: list[tuple[float, bool]] = []
    for case in cases:
        label = case.get("label")
        if label not in ("pass", "block"):
            continue
        result = reviewer.check(str(case.get("draft", "")), {"risk_level": "routine"})
        scores.append((result.risk_score, label == "block"))
    return scores


def sweep(scores: list[tuple[float, bool]]) -> list[ThresholdRow]:
    """对每个候选阈值计算 precision/recall/F1。

    正类为「应转人工」（label=block），预测为 ``score >= threshold``；
    无正样本时 precision/recall/F1 记 0。
    """
    positives = sum(1 for _, should_block in scores if should_block)
    rows: list[ThresholdRow] = []
    for threshold in THRESHOLDS:
        tp = sum(
            1 for score, should_block in scores if score >= threshold and should_block
        )
        predicted = sum(1 for score, _ in scores if score >= threshold)
        precision = tp / predicted if predicted else 0.0
        recall = tp / positives if positives else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        rows.append(ThresholdRow(threshold, round(precision, 4), round(recall, 4), round(f1, 4)))
    return rows


def best_threshold(rows: list[ThresholdRow]) -> float | None:
    """F1 最优阈值；F1 并列时取召回更高（更保守，宁可多转人工）。"""
    if not rows:
        return None
    best = max(rows, key=lambda r: (r.f1, r.recall, -r.threshold))
    return best.threshold


def _derive_from_feedback(rows: list[dict]) -> list[dict]:
    """从医生反馈集派生校准标注（数据飞轮 → 阈值校准的闭环）。

    - approve：草稿经医生认可 → ``pass``；
    - edit 且带修正文本：修正稿是医生认可的版本 → ``pass``（原始草稿的
      问题多为 citation/disclaimer 级提醒，标 block 会污染正类，不采用）；
    - 其余（reject / 无修正文本的 edit）：无法可靠给出草稿级标注，跳过。
    """
    out: list[dict] = []
    for row in rows:
        decision = row.get("decision")
        if decision == "approve" and row.get("draft"):
            out.append({"draft": str(row["draft"]), "label": "pass", "source": "feedback"})
        elif decision == "edit" and row.get("corrected"):
            out.append({"draft": str(row["corrected"]), "label": "pass", "source": "feedback"})
    return out


def load_labeled_cases(include_feedback: bool = False) -> list[dict]:
    """加载校准标注集；``include_feedback`` 时并入反馈集派生样本并按草稿去重。"""
    cases = list(_load("qc_calibration"))
    if not include_feedback:
        return cases
    seen = {str(case.get("draft")) for case in cases}
    for derived in _derive_from_feedback(_load("feedback_cases")):
        if derived["draft"] not in seen:
            seen.add(derived["draft"])
            cases.append(derived)
    return cases


def run_calibration(
    provider: LLMProvider,
    report_path: str = CALIBRATION_REPORT,
    include_feedback: bool = False,
) -> dict:
    """跑完整校准流程并输出 Markdown 报告。

    Args:
        provider: real 模式的 LLM 提供者（mock 评审员打分无语义意义）。
        report_path: 校准报告输出路径。
        include_feedback: 并入反馈集派生的标注（数据飞轮闭环）。

    Returns:
        含 scores / rows / best_threshold / report 的结果字典。
    """
    cases = load_labeled_cases(include_feedback=include_feedback)
    scores = collect_scores(cases, provider)
    rows = sweep(scores)
    best = best_threshold(rows)
    report = render_markdown(scores, rows, best)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    return {"scores": scores, "rows": rows, "best_threshold": best, "report": report}


def render_markdown(
    scores: list[tuple[float, bool]], rows: list[ThresholdRow], best: float | None
) -> str:
    blocked = sum(1 for _, should_block in scores if should_block)
    lines = [
        "# QC 风险阈值校准报告（设计文档 §9.4）",
        "",
        f"- 标注用例：{len(scores)}（其中应转人工 {blocked}）",
        f"- 推荐 CARE_QC_RISK_THRESHOLD：**{best if best is not None else '无'}**"
        + ("" if best is not None else "（无正样本或无数据）"),
        "",
        "| 阈值 | precision | recall | F1 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        marker = " ←" if row.threshold == best else ""
        lines.append(
            f"| {row.threshold} | {row.precision} | {row.recall} | {row.f1}{marker} |"
        )
    lines += [
        "",
        "> F1 并列时取召回更高者：医疗场景漏放行（false negative）的代价高于多转人工。",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import argparse
    import sys

    from care_lifeline.config import get_settings

    parser = argparse.ArgumentParser(description="QC 阈值校准（需 real 模式）")
    parser.add_argument("--mode", choices=["mock", "real"], default="real")
    parser.add_argument(
        "--include-feedback",
        action="store_true",
        help="并入反馈集派生标注（approve→pass；edit 取医生修正稿）",
    )
    args = parser.parse_args()

    if args.mode != "real":
        print("错误：校准依赖 LLM 语义评审打分，仅支持 --mode real（CARE_LLM_MODE=real）")
        sys.exit(2)
    settings = get_settings()
    if settings.llm_mode != "real":
        print("错误：需要 CARE_LLM_MODE=real")
        sys.exit(2)
    from care_lifeline.llm.real_provider import RealProvider

    try:
        provider = RealProvider(settings)
    except RuntimeError as exc:
        print(f"错误：{exc}")
        sys.exit(2)

    outcome = run_calibration(provider, include_feedback=args.include_feedback)
    print(f"校准完成 -> {CALIBRATION_REPORT}")
    print(f"  推荐阈值: {outcome['best_threshold']}")
    print(f"  标注用例: {len(outcome['scores'])}")
