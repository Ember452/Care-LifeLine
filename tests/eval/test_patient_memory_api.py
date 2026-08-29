"""结构化纵向记忆的路由（/v1/patients/{id}/medications|allergies|followups）测试。"""

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/patients_mem.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _headers(client: TestClient) -> dict:
    return {"Authorization": f"Bearer {_token(client)}"}


def test_medication_crud_roundtrip(client: TestClient) -> None:
    h = _headers(client)
    created = client.post(
        "/v1/patients/1/medications", json={"name": "华法林", "dosage": "2.5mg"}, headers=h
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "active"

    listed = client.get("/v1/patients/1/medications", headers=h)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    stopped = client.delete(
        f"/v1/patients/1/medications/{body['id']}", headers=h
    )
    assert stopped.status_code == 200
    assert stopped.json() == {"ok": True}
    after = client.get("/v1/patients/1/medications", headers=h).json()
    assert after[0]["status"] == "stopped"


def test_allergy_and_followup_roundtrip(client: TestClient) -> None:
    h = _headers(client)
    allergy = client.post(
        "/v1/patients/1/allergies",
        json={"allergen": "青霉素", "reaction": "皮疹", "severity": "severe"},
        headers=h,
    )
    assert allergy.status_code == 200
    assert allergy.json()["severity"] == "severe"

    bad = client.post(
        "/v1/patients/1/allergies", json={"allergen": "x", "severity": "致命"}, headers=h
    )
    assert bad.status_code == 422  # severity 枚举校验

    followup = client.post(
        "/v1/patients/1/followups",
        json={"plan": "复查 INR", "due_date": "2026-09-15T10:00:00"},
        headers=h,
    )
    assert followup.status_code == 200
    fid = followup.json()["id"]

    done = client.post(f"/v1/patients/1/followups/{fid}/complete", headers=h)
    assert done.json() == {"ok": True}
    items = client.get("/v1/patients/1/followups", headers=h).json()
    assert items[0]["status"] == "done"


def test_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/v1/patients/1/medications").status_code == 401
    assert client.post("/v1/patients/1/allergies", json={"allergen": "x"}).status_code == 401
