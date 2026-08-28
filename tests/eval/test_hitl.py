import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
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


def _auth(client: TestClient) -> dict:
    return {"Authorization": f"Bearer {_token(client)}"}


def test_emergency_triggers_hitl_event(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "em1", "message": "我突然胸痛而且呼吸困难"},
        headers=_auth(client),
    )
    text = resp.text
    assert "event: hitl" in text
    assert "event: done" in text
    assert "转接人工" in text
    assert "胸痛" not in text


def test_clinician_reply_requires_auth(client: TestClient) -> None:
    resp = client.post("/v1/hitl/reply", json={"session_id": "x", "message": "请就医"})
    assert resp.status_code == 401


def test_clinician_reply_persists_and_queue(client: TestClient) -> None:
    auth = _auth(client)
    client.post(
        "/v1/chat/stream",
        json={"session_id": "q1", "message": "我突然胸痛"},
        headers=auth,
    )
    reply = client.post(
        "/v1/hitl/reply",
        json={"session_id": "q1", "message": "请立即前往急诊"},
        headers=auth,
    )
    assert reply.status_code == 200

    queue = client.get("/v1/hitl/queue", headers=auth)
    assert queue.status_code == 200
    assert any(item["session_id"] == "q1" for item in queue.json())
