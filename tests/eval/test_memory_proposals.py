"""记忆提议-确认流（ADR-0019）的端到端测试。"""

import pytest
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/proposals.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as c:
        yield c


def _token(client: TestClient, username: str = "demo", password: str = "demo123") -> str:
    resp = client.post("/v1/auth/login", data={"username": username, "password": password})
    return resp.json()["access_token"]


def _headers(client: TestClient, **creds: str) -> dict:
    return {"Authorization": f"Bearer {_token(client, **creds)}"}


def test_chat_extracts_proposal_then_confirm_applies(client: TestClient) -> None:
    """对话提到开始服药 → pending 提议 → 确认后以 extracted 溯源写入用药表。"""
    h = _headers(client)
    chat = client.post(
        "/v1/chat/stream",
        json={"session_id": "s-prop", "patient_id": 1, "message": "医生，我开始服用布洛芬了"},
        headers=h,
    )
    assert chat.status_code == 200

    proposals = client.get("/v1/patients/1/memory-proposals", headers=h).json()
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["kind"] == "medication"
    assert proposal["action"] == "add"
    assert proposal["payload"]["name"] == "布洛芬"
    assert "布洛芬" in proposal["excerpt"]

    confirmed = client.post(
        f"/v1/patients/1/memory-proposals/{proposal['id']}/confirm", headers=h
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert "布洛芬" in confirmed.json()["applied"]

    meds = client.get("/v1/patients/1/medications", headers=h).json()
    assert meds[0]["name"] == "布洛芬"
    assert meds[0]["provenance"] == "extracted"

    # 已处理：pending 列表为空
    assert client.get("/v1/patients/1/memory-proposals", headers=h).json() == []


def test_chat_proposal_dedupes_same_content(client: TestClient) -> None:
    """同患者同内容的 pending 提议去重：重复对话不产生第二条。"""
    h = _headers(client)
    for _ in range(2):
        client.post(
            "/v1/chat/stream",
            json={"session_id": "s-dup", "patient_id": 1, "message": "我开始服用布洛芬了"},
            headers=h,
        )
    proposals = client.get("/v1/patients/1/memory-proposals", headers=h).json()
    assert len(proposals) == 1


def test_reject_writes_no_memory(client: TestClient) -> None:
    h = _headers(client)
    client.post(
        "/v1/chat/stream",
        json={"session_id": "s-rej", "patient_id": 1, "message": "我对青霉素过敏"},
        headers=h,
    )
    proposals = client.get("/v1/patients/1/memory-proposals", headers=h).json()
    assert proposals[0]["kind"] == "allergy"

    rejected = client.post(
        f"/v1/patients/1/memory-proposals/{proposals[0]['id']}/reject", headers=h
    )
    assert rejected.json()["status"] == "rejected"
    assert client.get("/v1/patients/1/allergies", headers=h).json() == []


def test_stop_proposal_flow(client: TestClient) -> None:
    """停药提议：先手工录入在用药，对话提出停用，确认后 valid_to 关闭。"""
    h = _headers(client)
    client.post("/v1/patients/1/medications", json={"name": "华法林"}, headers=h)
    client.post(
        "/v1/chat/stream",
        json={"session_id": "s-stop", "patient_id": 1, "message": "我把华法林停用了"},
        headers=h,
    )
    proposals = client.get("/v1/patients/1/memory-proposals", headers=h).json()
    assert proposals[0]["action"] == "stop"

    confirmed = client.post(
        f"/v1/patients/1/memory-proposals/{proposals[0]['id']}/confirm", headers=h
    )
    assert "已停用" in confirmed.json()["applied"]
    assert client.get("/v1/patients/1/medications", headers=h).json() == []


def test_decide_twice_returns_404(client: TestClient) -> None:
    h = _headers(client)
    client.post(
        "/v1/chat/stream",
        json={"session_id": "s-twice", "patient_id": 1, "message": "我开始服用布洛芬了"},
        headers=h,
    )
    proposals = client.get("/v1/patients/1/memory-proposals", headers=h).json()
    pid = proposals[0]["id"]
    assert (
        client.post(f"/v1/patients/1/memory-proposals/{pid}/confirm", headers=h).status_code
        == 200
    )
    assert (
        client.post(f"/v1/patients/1/memory-proposals/{pid}/confirm", headers=h).status_code
        == 404
    )


def test_proposals_require_auth(client: TestClient) -> None:
    assert client.get("/v1/patients/1/memory-proposals").status_code == 401
    assert (
        client.post("/v1/patients/1/memory-proposals/1/confirm", json={}).status_code == 401
    )
