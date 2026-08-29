"""QC 阈值校准（eval/calibrate.py）的行为测试。"""

from care_lifeline.eval.calibrate import (
    ThresholdRow,
    best_threshold,
    collect_scores,
    render_markdown,
    sweep,
)


class _ScoredProvider:
    """按草稿关键词返回预设 risk_score 的桩评审 provider。"""

    def __init__(self, score_map: dict[str, float]) -> None:
        self._score_map = score_map

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: str = "strong"
    ) -> str:
        import json

        draft = str(messages[-1]["content"])
        score = next(v for k, v in self._score_map.items() if k in draft)
        return json.dumps({"risk_score": score, "violations": []})

    def stream(self, **kwargs: object) -> object:
        yield ""


def test_collect_scores_maps_labels() -> None:
    provider = _ScoredProvider({"高危": 0.9, "请补充症状": 0.1})
    cases = [
        {"draft": "高危草稿内容", "label": "block"},
        {"draft": "请补充症状持续时间", "label": "pass"},
        {"draft": "label 非法的用例应跳过", "label": "unknown"},
    ]
    scores = collect_scores(cases, provider)  # type: ignore[arg-type]
    assert scores == [(0.9, True), (0.1, False)]


def test_sweep_perfect_separation() -> None:
    scores = [(0.9, True), (0.85, True), (0.1, False), (0.2, False)]
    rows = sweep(scores)
    best_row = max(rows, key=lambda r: r.f1)
    # 网格上第一个把两类完全分开的阈值是 0.25（>0.2 且 <=0.85）。
    assert best_row.threshold == 0.25
    assert best_row.precision == 1.0
    assert best_row.recall == 1.0
    assert best_row.f1 == 1.0


def test_sweep_threshold_boundary_is_inclusive() -> None:
    # 预测口径为 score >= threshold：恰好等于阈值也应命中。
    rows = sweep([(0.75, True), (0.1, False)])
    at_075 = next(r for r in rows if r.threshold == 0.75)
    assert at_075.recall == 1.0
    assert at_075.precision == 1.0


def test_best_threshold_tie_prefers_higher_recall() -> None:
    # F1 并列（同为 1.0）时取召回更高者；仍并列取更小阈值。
    rows = [
        ThresholdRow(threshold=0.3, precision=1.0, recall=1.0, f1=1.0),
        ThresholdRow(threshold=0.5, precision=1.0, recall=0.5, f1=0.6667),
    ]
    assert best_threshold(rows) == 0.3
    assert best_threshold([]) is None


def test_render_markdown_marks_recommended_row() -> None:
    rows = sweep([(0.9, True), (0.1, False)])
    best = best_threshold(rows)
    text = render_markdown([(0.9, True), (0.1, False)], rows, best)
    assert "推荐 CARE_QC_RISK_THRESHOLD" in text
    assert "←" in text  # 推荐行有标记
    assert "漏放行" in text  # 决策依据说明


def test_sweep_no_positives_is_zero() -> None:
    rows = sweep([(0.1, False), (0.2, False)])
    assert all(r.recall == 0.0 and r.precision == 0.0 and r.f1 == 0.0 for r in rows)


def test_threshold_grid_covers_range() -> None:
    from care_lifeline.eval.calibrate import THRESHOLDS

    assert THRESHOLDS[0] == 0.05
    assert THRESHOLDS[-1] == 0.95
    assert len(THRESHOLDS) == 19


def test_derive_from_feedback_approve_and_edit() -> None:
    from care_lifeline.eval.calibrate import _derive_from_feedback

    rows = [
        {"decision": "approve", "draft": "医生认可的草稿"},
        {"decision": "edit", "draft": "有问题的草稿", "corrected": "医生修正稿"},
        {"decision": "edit", "draft": "无修正文本，无法标注"},
        {"decision": "reject", "draft": "被驳回的草稿"},
    ]
    derived = _derive_from_feedback(rows)
    # 只有 approve 草稿与 edit 修正稿能可靠标注为 pass
    assert derived == [
        {"draft": "医生认可的草稿", "label": "pass", "source": "feedback"},
        {"draft": "医生修正稿", "label": "pass", "source": "feedback"},
    ]


def test_load_labeled_cases_with_feedback_dedupes() -> None:
    from care_lifeline.eval.calibrate import load_labeled_cases

    base = load_labeled_cases(include_feedback=False)
    expanded = load_labeled_cases(include_feedback=True)
    assert len(expanded) >= len(base)
    drafts = [str(c["draft"]) for c in expanded]
    assert len(drafts) == len(set(drafts))  # 按草稿去重
    labels = {c["label"] for c in expanded}
    assert labels <= {"pass", "block"}
