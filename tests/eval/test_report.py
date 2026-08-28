from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/report.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_interpret_requires_auth(client: TestClient) -> None:
    resp = client.post("/v1/report/interpret", json={"text": "血压：150"})
    assert resp.status_code == 401


def test_interpret_returns_fields(client: TestClient) -> None:
    token = _token(client)
    resp = client.post(
        "/v1/report/interpret",
        json={"text": "血压：150/95（参考 90-140）\n血糖：7.8（参考 3.9-6.1）偏高"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any("血压" in f["name"] for f in body["fields"])
    assert any(f["abnormal"] for f in body["fields"])
