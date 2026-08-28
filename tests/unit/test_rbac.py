from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing

_ROLES: dict[str, tuple[str, str]] = {
    "admin": ("admin", "admin123"),
    "clinician": ("doctor", "doctor123"),
    "patient": ("demo", "demo123"),
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/rbac.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c
    reset_state_for_testing()


def _token(client: TestClient, role: str) -> str:
    username, password = _ROLES[role]
    resp = client.post("/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(client: TestClient, role: str) -> dict:
    return {"Authorization": f"Bearer {_token(client, role)}"}


def test_login_response_includes_role(client: TestClient) -> None:
    body = client.post("/v1/auth/login", data={"username": "admin", "password": "admin123"}).json()
    assert body["role"] == "admin"


def test_patient_forbidden_on_admin_endpoint(client: TestClient) -> None:
    resp = client.get("/v1/admin/metrics", headers=_headers(client, "patient"))
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_patient_forbidden_on_workbench_endpoint(client: TestClient) -> None:
    resp = client.get("/v1/workbench/queue", headers=_headers(client, "patient"))
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_patient_forbidden_on_hitl_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/v1/hitl/reply",
        json={"session_id": "x", "message": "请就医"},
        headers=_headers(client, "patient"),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_clinician_allowed_on_workbench(client: TestClient) -> None:
    resp = client.get("/v1/workbench/queue", headers=_headers(client, "clinician"))
    assert resp.status_code == 200


def test_clinician_forbidden_on_admin_endpoint(client: TestClient) -> None:
    resp = client.get("/v1/admin/metrics", headers=_headers(client, "clinician"))
    assert resp.status_code == 403


def test_admin_allowed_on_admin_and_workbench(client: TestClient) -> None:
    assert client.get("/v1/admin/metrics", headers=_headers(client, "admin")).status_code == 200
    assert client.get("/v1/workbench/queue", headers=_headers(client, "admin")).status_code == 200
    assert client.get("/v1/hitl/queue", headers=_headers(client, "admin")).status_code == 200


def test_any_logged_in_user_can_chat(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/stream",
        json={"session_id": "r1", "message": "我最近有点咳嗽"},
        headers=_headers(client, "patient"),
    )
    assert resp.status_code == 200
    assert "event: done" in resp.text
