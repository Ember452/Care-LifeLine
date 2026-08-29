"""Trajectory 端点与审计轨迹（批次 1）的行为测试。"""

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from care_lifeline.api import runtime
from care_lifeline.api.app import app
from care_lifeline.config import get_settings
from care_lifeline.db.engine import reset_state_for_testing


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/traj.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    runtime.reset_runtime_metrics()
    with TestClient(app) as c:
        yield c


def _admin_token(client: TestClient) -> str:
    resp = client.post("/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _headers(client: TestClient) -> dict:
    return {"Authorization": f"Bearer {_admin_token(client)}"}


def test_persist_writes_tool_and_qc_audit(client: TestClient) -> None:
    """medication 对话落库后，审计流应含 tool_called 与 qc_decision 事件。"""
    client.post(
        "/v1/chat/stream",
        json={"session_id": "s-traj", "message": "华法林，阿司匹林 一起吃有相互作用吗"},
        headers=_headers(client),
    )
    resp = client.get("/v1/admin/audit?limit=50", headers=_headers(client))
    assert resp.status_code == 200
    events = [row["event"] for row in resp.json()]
    assert "tool_called" in events
    assert "qc_decision" in events
    tool_rows = [r for r in resp.json() if r["event"] == "tool_called"]
    detail = tool_rows[0]["detail"]
    assert "drug_interaction" in detail
    qc_rows = [r for r in resp.json() if r["event"] == "qc_decision"]
    assert '"status"' in qc_rows[0]["detail"]


def test_checkpoints_requires_persistence(client: TestClient, monkeypatch) -> None:
    """无 checkpointer 时时间旅行端点返回 409（而非 500）。"""
    from care_lifeline.api.routers import trajectories

    monkeypatch.setattr(trajectories, "get_checkpointer", lambda: None)
    resp = client.get("/v1/admin/trajectories/s-x/checkpoints", headers=_headers(client))
    assert resp.status_code == 409
    assert resp.json()["code"] == "checkpointer_unavailable"


def test_checkpoints_list_and_replay(client: TestClient, monkeypatch) -> None:
    """有 checkpointer：跑完一轮会话后可列出检查点，并从早期检查点重放到 END。"""
    from care_lifeline.graph.builder import build_graph
    from care_lifeline.graph.state import AgentState
    from care_lifeline.llm.mock_provider import MockProvider

    saver = MemorySaver()
    from langchain_core.messages import HumanMessage

    from care_lifeline.api.routers import trajectories

    monkeypatch.setattr(trajectories, "get_checkpointer", lambda: saver)

    # 用与端点相同的图配置直跑一轮完整会话，产生检查点历史
    state: AgentState = {
        "messages": [HumanMessage("最近化验单说贫血")],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
        "retry_count": 0,
        "memory_context": "",
    }
    graph = build_graph(MockProvider(), checkpointer=saver)
    import asyncio

    asyncio.run(
        graph.ainvoke(state, config={"configurable": {"thread_id": "s-replay"}})
    )

    # 列检查点：应非空且含 checkpoint_id
    resp = client.get("/v1/admin/trajectories/s-replay/checkpoints", headers=_headers(client))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    assert all(item["checkpoint_id"] for item in items)

    # 从最早的检查点重放：应能重新执行到 END 并产出 draft
    earliest = items[-1]["checkpoint_id"]
    replay = client.post(
        "/v1/admin/trajectories/s-replay/replay",
        json={"checkpoint_id": earliest},
        headers=_headers(client),
    )
    assert replay.status_code == 200
    body = replay.json()
    assert body["ok"] is True
    assert body["final"]

    # 重放动作写审计
    audit = client.get(
        "/v1/admin/audit?event=trajectory_replayed", headers=_headers(client)
    )
    assert audit.status_code == 200
    assert len(audit.json()) == 1
