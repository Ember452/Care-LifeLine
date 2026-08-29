from __future__ import annotations

import pytest

from care_lifeline.config import get_settings
from care_lifeline.db import session_store
from care_lifeline.db.engine import init_db, reset_state_for_testing


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/store.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    yield
    reset_state_for_testing()


def test_seed_demo_user_creates_three_roles(db) -> None:
    session_store.seed_demo_user()
    assert session_store.verify_user("admin", "admin123") is not None
    assert session_store.verify_user("doctor", "doctor123") is not None
    assert session_store.verify_user("demo", "demo123") is not None
    admin = session_store.get_user_by_username("admin")
    assert admin.role == "admin"
    doctor = session_store.get_user_by_username("doctor")
    assert doctor.role == "clinician"


def test_create_user_with_role(db) -> None:
    user = session_store.create_user("nurse", "nurse123", role="clinician")
    assert user.role == "clinician"
    assert session_store.verify_user("nurse", "nurse123") is not None


def test_delete_session_removes_messages_and_audit(db) -> None:
    session = session_store.get_or_create_session("del-1", user_id=1, title="t")
    session_store.append_message(session.id, "user", "我头痛")
    session_store.write_audit(session.id, "chat_completed", "demo")
    assert session_store.delete_session("del-1") is True
    assert session_store.get_session_by_thread_id("del-1") is None
    assert session_store.delete_session("del-1") is False


def test_list_audit_logs_filters_and_paginates(db) -> None:
    session = session_store.get_or_create_session("aud-1", user_id=1, title="t")
    session_store.write_audit(session.id, "chat_completed", "demo")
    session_store.write_audit(None, "phi_leak", "type=phone")
    all_rows = session_store.list_audit_logs()
    assert len(all_rows) == 2
    leaks = session_store.list_audit_logs(event="phi_leak")
    assert len(leaks) == 1
    assert leaks[0].detail == "type=phone"
    one = session_store.list_audit_logs(limit=1, offset=0)
    assert len(one) == 1


def test_qc_rule_sync_and_toggle_persist(db) -> None:
    """规则启停落库（P1-D）：同步建行、toggle 落库、状态可恢复。"""
    from care_lifeline.safety import rules_engine

    defs = rules_engine.rule_definitions()
    assert len(defs) >= 9
    states = session_store.sync_qc_rules(defs)
    # 首次同步：全部默认启用
    assert all(states.values()) is True or set(states.values()) == {True}

    # 落库停用 + 引擎加载
    assert session_store.set_qc_rule_enabled("off_scope", False) is True
    assert session_store.set_qc_rule_enabled("no_such_rule", True) is False
    rules_engine.apply_rule_states(session_store.sync_qc_rules(defs))
    assert rules_engine.is_rule_enabled("off_scope") is False

    # 再次同步保留运维状态；恢复启用后引擎一致
    assert session_store.set_qc_rule_enabled("off_scope", True) is True
    rules_engine.apply_rule_states(session_store.sync_qc_rules(defs))
    assert rules_engine.is_rule_enabled("off_scope") is True
