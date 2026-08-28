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


def _token(client: TestClient, username: str = "demo", password: str = "demo123") -> str:
    resp = client.post("/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(client: TestClient, username: str = "demo", password: str = "demo123") -> dict:
    return {"Authorization": f"Bearer {_token(client, username, password)}"}


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
    # hitl/* 仅 clinician/admin（契约 §6），用 doctor 登录。
    auth = _auth(client, "doctor", "doctor123")
    client.post(
        "/v1/chat/stream",
        json={"session_id": "q1", "message": "我突然胸痛"},
        headers=_auth(client),
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


def test_hitl_resume_degrades_without_checkpointer(client: TestClient) -> None:
    # SQLite 无 checkpointer：resume 降级为软 HITL，绝不阻塞。
    auth = _auth(client, "doctor", "doctor123")
    client.post(
        "/v1/chat/stream",
        json={"session_id": "r1", "message": "我突然胸痛"},
        headers=_auth(client),
    )
    resp = client.post(
        "/v1/hitl/resume",
        json={"session_id": "r1", "decision": "approve", "corrected_text": "请立即就医"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_patient_denied_hitl(client: TestClient) -> None:
    resp = client.post(
        "/v1/hitl/reply",
        json={"session_id": "x", "message": "请就医"},
        headers=_auth(client, "demo", "demo123"),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"
