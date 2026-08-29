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


def _token(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    resp = client.post("/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_metrics_structure(client: TestClient) -> None:
    token = _token(client)
    resp = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "refuse_rate",
        "refusal_rate",
        "leak_rate",
        "faithfulness",
        "compliance",
        "hitl_rate",
        "p95_ms",
        "total_sessions",
        "total_messages",
        "pending_reviews",
    ):
        assert key in data
    assert data["faithfulness"] == 1.0
    assert data["compliance"] == 1.0


def test_metrics_exposes_runtime_observability(client: TestClient) -> None:
    """聊天后 /admin/metrics 应带出节点延迟、质控计数与 token 用量。"""
    from care_lifeline.api.runtime import reset_runtime_metrics

    reset_runtime_metrics()
    token = _token(client)
    client.post(
        "/v1/chat/stream",
        json={"session_id": "s-obs", "message": "最近有点头晕"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    # 节点延迟：本次请求经过的节点都有采样
    assert "triage" in data["node_latency"]
    assert data["node_latency"]["triage"]["count"] >= 1
    assert "p95_ms" in data["node_latency"]["triage"]
    # 质控计数：一次通过
    assert data["qc_status_counts"].get("passed", 0) >= 1
    # token 用量：mock 为估算值，但计数与字段齐全
    tokens = data["token_usage"]
    assert tokens["request_count"] >= 1
    assert tokens["total_input_tokens"] > 0
    assert tokens["estimated_request_count"] == tokens["request_count"]  # mock 全为估算
    session_row = tokens["sessions"].get("s-obs")
    assert session_row is not None
    assert session_row["output_tokens"] > 0


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


def test_rule_toggle_writes_audit(client: TestClient) -> None:
    token = _token(client)
    client.put(
        "/v1/admin/rules",
        json={"code": "emergency", "enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.get("/v1/admin/audit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert any(item["event"] == "qc_rule_toggled" for item in resp.json())


def test_admin_audit_pagination(client: TestClient) -> None:
    token = _token(client)
    session_store.write_audit(1, "chat_completed", "x")
    session_store.write_audit(1, "phi_leak", "type=phone")
    resp = client.get(
        "/v1/admin/audit?limit=1&offset=0", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    filtered = client.get(
        "/v1/admin/audit?event=phi_leak", headers={"Authorization": f"Bearer {token}"}
    )
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["event"] == "phi_leak"


def test_admin_denied_for_patient(client: TestClient) -> None:
    token = _token(client, username="demo", password="demo123")
    resp = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"
