import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/chat.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_stream_event_order(client: TestClient) -> None:
    token = _token(client)
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s1", "message": "最近化验单说贫血"},
        headers={"Authorization": f"Bearer {token}"},
    )
    text = resp.text
    assert "event: meta" in text
    assert "event: token" in text
    assert "event: qc" in text
    assert "event: done" in text

    meta = text.index("event: meta")
    token_idx = text.index("event: token")
    qc = text.index("event: qc")
    done = text.index("event: done")
    assert meta < token_idx < qc < done


def test_empty_message_returns_error_event(client: TestClient) -> None:
    token = _token(client)
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s1", "message": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert "event: error" in resp.text


def test_unauthorized_without_token(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s1", "message": "最近化验单说贫血"},
    )
    assert resp.status_code == 401


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_index_serves_html(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Care-LifeLine" in resp.text


def test_sessions_requires_auth(client: TestClient) -> None:
    resp = client.get("/v1/sessions")
    assert resp.status_code == 401


def test_sessions_lists_after_chat(client: TestClient) -> None:
    token = _token(client)
    client.post(
        "/v1/chat/stream",
        json={"session_id": "s-list", "message": "最近有点头痛"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.get("/v1/sessions", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    ids = [item["session_id"] for item in resp.json()]
    assert "s-list" in ids
