from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/smoke.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _chat(client: TestClient, token: str, text: str) -> str:
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "smoke", "message": text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.text


def test_full_stack_smoke(client: TestClient) -> None:
    token = _token(client)

    # 普通对话：正常通过
    normal = _chat(client, token, "我最近咳嗽，有点发烧")
    assert "event: done" in normal
    assert '"status": "passed"' in normal

    # 高风险对话：转人工，并落入待审队列
    hitl = _chat(client, token, "我现在胸痛得厉害")
    assert "event: hitl" in hitl

    queue = client.get("/v1/workbench/queue", headers={"Authorization": f"Bearer {token}"})
    assert queue.status_code == 200
    assert len(queue.json()) == 1
    review_id = queue.json()[0]["id"]

    # 医生审核通过，队列清空
    reviewed = client.post(
        f"/v1/workbench/items/{review_id}/review",
        json={"decision": "approve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approve"
    assert client.get(
        "/v1/workbench/queue", headers={"Authorization": f"Bearer {token}"}
    ).json() == []

    # 报告解读
    report = client.post(
        "/v1/report/interpret",
        json={"text": "血压：150/95 mmHg（参考范围 <140/90）"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert report.status_code == 200
    assert report.json()["fields"]

    # 慢病记忆 + 提醒
    metric = client.post(
        "/v1/patients/1/metrics",
        json={"name": "收缩压", "value": 150.0, "unit": "mmHg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert metric.status_code == 200
    reminders = client.get(
        "/v1/patients/1/reminders", headers={"Authorization": f"Bearer {token}"}
    )
    assert any(r["metric"] == "收缩压" for r in reminders.json())

    # 管理后台指标可见
    metrics = client.get("/v1/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert metrics.status_code == 200
    assert "refuse_rate" in metrics.json()
