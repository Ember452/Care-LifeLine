from __future__ import annotations

import json

import pytest

from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import init_db, reset_state_for_testing
from care_lifeline.eval.promote import promote_review


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/prom.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    yield
    reset_state_for_testing()


def test_promote_review_writes_case(db, tmp_path) -> None:
    session = session_store.get_or_create_session("sess-p", user_id=1, title="t")
    review = session_store.create_hitl_review(
        session_id=session.id,
        thread_id="sess-p",
        input_text="胸痛",
        draft="请服药",
        violations_json='["emergency"]',
    )
    session_store.resolve_review(review.id, "edit", "doctor", "请立即就医")

    path = str(tmp_path / "feedback_cases.json")
    case = promote_review(session_store.get_review(review.id), path)

    assert case["decision"] == "edit"
    assert case["corrected"] == "请立即就医"
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved[0]["thread_id"] == "sess-p"
    assert saved[0]["violations"] == ["emergency"]


def test_promote_requires_decision(db, tmp_path) -> None:
    session = session_store.get_or_create_session("sess-p2", user_id=1, title="t")
    review = session_store.create_hitl_review(
        session_id=session.id, thread_id="sess-p2", input_text="x", draft="y"
    )
    path = str(tmp_path / "feedback_cases.json")
    try:
        promote_review(review, path)
        raise AssertionError("应因未审核而抛错")
    except ValueError:
        pass
