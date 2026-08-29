from __future__ import annotations

import json
import os

from care_lifeline.config import get_settings
from care_lifeline.db.models import HitlReview


def _default_path() -> str:
    return get_settings().feedback_data_path


def _load(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, cases: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)


def promote_review(review: HitlReview, path: str | None = None) -> dict:
    """Persist a clinician review decision as an eval case.

    Feedback is written to a dedicated dataset (not the RAG guideline corpus),
    so it never leaks into retrieval context. 缺省路径来自
    ``CARE_FEEDBACK_DATA_PATH``（测试必须重定向，避免污染真实评测数据）。
    """
    if review.decision is None:
        raise ValueError("未审核的审阅项不能转为评测样本")

    case = {
        "source": "clinician_feedback",
        "thread_id": review.thread_id,
        "input": review.input_text,
        "draft": review.draft,
        "decision": review.decision,
        "corrected": review.corrected_text,
        "violations": json.loads(review.violations_json or "[]"),
    }
    resolved_path = path or _default_path()
    cases = _load(resolved_path)
    cases.append(case)
    _save(resolved_path, cases)
    return case
