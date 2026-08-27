from fastapi.testclient import TestClient

from care_lifeline.api.app import app

client = TestClient(app)


def test_stream_event_order() -> None:
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s1", "message": "最近化验单说贫血"},
    )
    text = resp.text
    assert "event: meta" in text
    assert "event: token" in text
    assert "event: qc" in text
    assert "event: done" in text

    meta = text.index("event: meta")
    token = text.index("event: token")
    qc = text.index("event: qc")
    done = text.index("event: done")
    assert meta < token < qc < done


def test_empty_message_returns_error_event() -> None:
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s1", "message": "   "},
    )
    assert "event: error" in resp.text


def test_health_ok() -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
