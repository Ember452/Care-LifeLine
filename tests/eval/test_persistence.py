from __future__ import annotations

from langchain_core.messages import HumanMessage
from sqlalchemy import select

from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import get_sessionmaker, init_db, reset_state_for_testing
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider


def _initial_state(message: str) -> AgentState:
    return {
        "messages": [HumanMessage(message)],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
    }


def _sqlite_env(monkeypatch, tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/m2.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()


def test_session_store_persists_messages_and_audit(monkeypatch, tmp_path) -> None:
    _sqlite_env(monkeypatch, tmp_path)
    init_db()

    session = session_store.get_or_create_session("t1", title="头痛咨询")
    session_store.append_message(session.id, "user", "我头痛")
    session_store.append_message(
        session.id,
        "assistant",
        "建议休息",
        citations=[{"index": 1, "source": "指南", "snippet": "x"}],
    )
    session_store.write_audit(session.id, "chat_completed")

    sessions = session_store.list_sessions()
    assert len(sessions) == 1

    maker = get_sessionmaker()
    from care_lifeline.db.models import Message

    with maker() as db:
        rows = db.execute(select(Message).where(Message.session_id == session.id)).scalars().all()
    assert len(rows) == 2
    assert rows[1].citations == [{"index": 1, "source": "指南", "snippet": "x"}]


def test_recovery_loads_prior_messages_in_order(monkeypatch, tmp_path) -> None:
    _sqlite_env(monkeypatch, tmp_path)
    init_db()

    session = session_store.get_or_create_session("t2")
    session_store.append_message(session.id, "user", "我最近头痛")
    session_store.append_message(session.id, "assistant", "建议多休息")
    session_store.append_message(session.id, "user", "还有点咳嗽")

    prior = session_store.get_prior_messages(session.id)
    assert [type(m).__name__ for m in prior] == ["HumanMessage", "AIMessage", "HumanMessage"]
    assert "咳嗽" in prior[-1].content

    initial = _initial_state("需要复诊建议")
    initial["messages"] = prior + initial["messages"]
    graph = build_graph(MockProvider())
    state = graph.invoke(initial)
    assert len(state["messages"]) >= 4


def test_chat_endpoint_persists_and_recovers(monkeypatch, tmp_path) -> None:
    _sqlite_env(monkeypatch, tmp_path)
    init_db()

    from fastapi.testclient import TestClient

    from care_lifeline.api.app import app

    with TestClient(app) as client:
        token = client.post(
            "/v1/auth/login", data={"username": "demo", "password": "demo123"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        r1 = client.post(
            "/v1/chat/stream",
            json={"session_id": "conv-1", "message": "我最近头痛"},
            headers=headers,
        )
        assert "event: done" in r1.text
        r2 = client.post(
            "/v1/chat/stream",
            json={"session_id": "conv-1", "message": "还有点咳嗽"},
            headers=headers,
        )
        assert "event: done" in r2.text

    rows = session_store.get_messages(session_store.get_or_create_session("conv-1").id)
    contents = [m.content for m in rows]
    assert any("头痛" in c for c in contents)
    assert any("咳嗽" in c for c in contents)
