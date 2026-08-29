"""单会话 token 预算护栏（文档 §10.4）的行为测试。"""

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api import runtime
from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing
from care_lifeline.llm.provider import TokenUsage


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/budget.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    runtime.reset_runtime_metrics()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    return resp.json()["access_token"]


def test_no_budget_by_default_allows_chat(client: TestClient) -> None:
    token = _token(client)
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s-free", "message": "最近有点头晕"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert "event: done" in resp.text
    assert "token_budget_exceeded" not in resp.text


def test_budget_exceeded_degrades_with_error_event(client: TestClient, monkeypatch) -> None:
    """预算=1 且会话已有累计用量：请求被拦截且不产出回复。"""
    monkeypatch.setenv("CARE_SESSION_TOKEN_BUDGET", "1")
    get_settings.cache_clear()
    runtime.reset_runtime_metrics()
    runtime.record_token_usage("s-capped", TokenUsage(input_tokens=50, output_tokens=50))
    token = _token(client)
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "s-capped", "message": "最近有点头晕"},
        headers={"Authorization": f"Bearer {token}"},
    )
    text = resp.text
    assert '"token_budget_exceeded"' in text
    assert "event: done" not in text

    # 拦截动作写审计
    admin = client.post("/v1/auth/login", data={"username": "admin", "password": "admin123"})
    admin_token = admin.json()["access_token"]
    audit = client.get(
        "/v1/admin/audit?event=token_budget_exceeded",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert audit.status_code == 200
    assert len(audit.json()) == 1


def test_session_tokens_accumulates_then_guard_trips(client: TestClient, monkeypatch) -> None:
    """第一轮计入用量后，第二轮撞上预算线被拦（护栏按会话累计生效）。"""
    monkeypatch.setenv("CARE_SESSION_TOKEN_BUDGET", "10")
    get_settings.cache_clear()
    runtime.reset_runtime_metrics()
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/v1/chat/stream",
        json={"session_id": "s-acc", "message": "最近有点头晕"},
        headers=headers,
    )
    assert "event: done" in first.text
    assert runtime.session_tokens("s-acc") >= 10

    second = client.post(
        "/v1/chat/stream",
        json={"session_id": "s-acc", "message": "还要注意什么"},
        headers=headers,
    )
    assert '"token_budget_exceeded"' in second.text
