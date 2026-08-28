from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import reset_state_for_testing
from care_lifeline.safety import rules_engine


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/admin.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_metrics_structure(client: TestClient) -> None:
    token = _token(client)
    resp = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    for key in ("refuse_rate", "leak_rate", "faithfulness", "compliance", "hitl_rate", "p95_ms"):
        assert key in data
    assert data["faithfulness"] == 1.0
    assert data["compliance"] == 1.0


def test_audit_trace_returns_messages(client: TestClient) -> None:
    token = _token(client)
    s = session_store.get_or_create_session("sess-a", user_id=1, title="t")
    session_store.append_message(s.id, "user", "我头痛")
    session_store.write_audit(s.id, "chat_completed", "demo")
    resp = client.get(
        "/v1/admin/audit/sessions/sess-a", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["content"] == "我头痛"
    assert any(a["event"] == "chat_completed" for a in resp.json()["audit"])


def test_rules_toggle(client: TestClient) -> None:
    token = _token(client)
    before = client.get("/v1/admin/rules", headers={"Authorization": f"Bearer {token}"})
    assert before.status_code == 200
    assert any(r["code"] == "emergency" for r in before.json())

    off = client.put(
        "/v1/admin/rules",
        json={"code": "emergency", "enabled": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert off.status_code == 200
    assert off.json()["enabled"] is False
    assert rules_engine.is_rule_enabled("emergency") is False

    client.put(
        "/v1/admin/rules",
        json={"code": "emergency", "enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
