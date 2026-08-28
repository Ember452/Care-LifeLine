from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/hitl.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _make_review() -> int:
    session = session_store.get_or_create_session("sess-h", user_id=1, title="高风险")
    review = session_store.create_hitl_review(
        session_id=session.id,
        thread_id="sess-h",
        input_text="我现在胸痛",
        draft="请服药",
        qc_json='{"status":"hitl","risk_score":0.9,"violations":["emergency"]}',
        violations_json='["emergency"]',
    )
    return review.id


def test_queue_requires_auth(client: TestClient) -> None:
    assert client.get("/v1/workbench/queue").status_code == 401


def test_queue_and_review_flow(client: TestClient) -> None:
    token = _token(client)
    rid = _make_review()

    queue = client.get("/v1/workbench/queue", headers={"Authorization": f"Bearer {token}"})
    assert queue.status_code == 200
    assert len(queue.json()) == 1
    assert queue.json()[0]["input_text"] == "我现在胸痛"

    item = client.get(
        f"/v1/workbench/items/{rid}", headers={"Authorization": f"Bearer {token}"}
    )
    assert item.json()["violations"] == ["emergency"]

    approved = client.post(
        f"/v1/workbench/items/{rid}/review",
        json={"decision": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approve"

    queue_after = client.get(
        "/v1/workbench/queue", headers={"Authorization": f"Bearer {token}"}
    )
    assert queue_after.json() == []


def test_edit_requires_corrected_text(client: TestClient) -> None:
    token = _token(client)
    rid = _make_review()
    bad = client.post(
        f"/v1/workbench/items/{rid}/review",
        json={"decision": "edit"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 422

    ok = client.post(
        f"/v1/workbench/items/{rid}/review",
        json={"decision": "edit", "corrected_text": "请立即就医"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    assert ok.json()["corrected_text"] == "请立即就医"
