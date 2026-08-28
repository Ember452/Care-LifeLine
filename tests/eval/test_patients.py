from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/patients.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_add_metric_requires_auth(client: TestClient) -> None:
    resp = client.post("/v1/patients/1/metrics", json={"name": "收缩压", "value": 150.0})
    assert resp.status_code == 401


def test_metric_and_reminder_flow(client: TestClient) -> None:
    token = _token(client)
    add = client.post(
        "/v1/patients/1/metrics",
        json={"name": "收缩压", "value": 150.0, "unit": "mmHg"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add.status_code == 200
    assert add.json()["value"] == 150.0

    reminders = client.get("/v1/patients/1/reminders", headers={"Authorization": f"Bearer {token}"})
    assert reminders.status_code == 200
    assert any(r["metric"] == "收缩压" for r in reminders.json())
