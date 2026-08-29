"""P1-F 回归：患者纵向记忆接入图。"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from care_lifeline.config import get_settings
from care_lifeline.db.engine import init_db, reset_state_for_testing
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.nodes.memory import memory_recall_node
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider
from care_lifeline.memory import patient_memory


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/mem.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    get_settings.cache_clear()
    reset_state_for_testing()
    init_db()
    yield
    reset_state_for_testing()


def _state(text: str, patient_id: int | None = None) -> AgentState:
    return {
        "messages": [HumanMessage(text)],
        "patient_id": patient_id,
        "intent": "",
        "risk_level": "routine",
        "scope_result": None,
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[typeddict-item]
        "hitl_required": False,
        "report": None,
        "medication_warnings": [],
        "retry_count": 0,
        "memory_context": "",
    }


