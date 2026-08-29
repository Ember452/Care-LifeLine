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


def test_stream_done_event_includes_token_usage(client: TestClient) -> None:
    """done 事件附带本请求 token 用量（mock 为估算值，字段齐全）。"""
    token = _token(client)
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s-usage", "message": "最近有点头痛"},
        headers={"Authorization": f"Bearer {token}"},
    )
    text = resp.text
    done = text[text.index("event: done") :]
    assert '"token_usage"' in done
    assert '"input"' in done and '"output"' in done
    assert '"estimated": true' in done


def test_empty_message_returns_422(client: TestClient) -> None:
    token = _token(client)
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s1", "message": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 契约 §1：空输入等客户端错误先返回 4xx，不再用 HTTP 200 包错误事件。
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_request"


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
    assert "text/html" in resp.headers["content-type"]
    # 根路径提供前端：React SPA（<div id="root">）或静态页（Care-LifeLine）
    assert '<div id="root">' in resp.text or "Care-LifeLine" in resp.text


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


def test_stream_medication_emits_real_tool_call(client: TestClient) -> None:
    """tool_call 事件来自真实工具轨迹：medication 意图应发出 drug_interaction 调用。"""
    token = _token(client)
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s-tool", "message": "华法林和阿司匹林能一起吃吗"},
        headers={"Authorization": f"Bearer {token}"},
    )
    text = resp.text
    assert "event: tool_call" in text
    assert '"drug_interaction"' in text
    # 轨迹事件先于 token 流（模型基于工具结果作答）。
    tool_idx = text.index("event: tool_call")
    qc_idx = text.index("event: qc")
    assert tool_idx < qc_idx
