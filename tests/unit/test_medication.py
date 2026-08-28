from care_lifeline.tools.medication import MedicationAgent


def test_extract_drugs_splits_on_common_separators() -> None:
    agent = MedicationAgent()
    drugs = agent.extract_drugs("华法林，阿司匹林、布洛芬")
    assert "华法林" in drugs
    assert "阿司匹林" in drugs
    assert "布洛芬" in drugs


def test_check_interactions_finds_known_pair() -> None:
    agent = MedicationAgent()
    hits = agent.check_interactions(["华法林", "阿司匹林"])
    assert len(hits) == 1
    assert hits[0].a == "华法林"
    assert hits[0].b == "阿司匹林"
    assert hits[0].severity == "major"


def test_check_interactions_no_false_positive() -> None:
    agent = MedicationAgent()
    assert agent.check_interactions(["维生素C", "钙片"]) == []


def test_warnings_text_includes_note() -> None:
    agent = MedicationAgent()
    warnings = agent.warnings(["华法林", "布洛芬"])
    assert len(warnings) == 1
    assert "NSAIDs" in warnings[0]
