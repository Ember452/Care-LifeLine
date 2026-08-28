from __future__ import annotations

from care_lifeline.graph.state import AgentState, last_user_text
from care_lifeline.tools.medication import MedicationAgent


def medication_node(state: AgentState, provider) -> dict:
    text = last_user_text(state["messages"])
    agent = MedicationAgent()
    drugs = agent.extract_drugs(text)
    warnings = agent.warnings(drugs)
    return {"medication_warnings": warnings}
