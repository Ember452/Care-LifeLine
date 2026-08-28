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


def test_ddi_table_has_at_least_twenty_entries() -> None:
    from care_lifeline.tools.medication import _DDI_TABLE

    assert len(_DDI_TABLE) >= 20


def test_normalize_maps_alias_to_canonical() -> None:
    agent = MedicationAgent()
    assert agent.normalize("拜阿司匹灵") == "阿司匹林"
    assert agent.normalize("格华止") == "二甲双胍"
    assert agent.normalize("维生素C") == "维生素C"  # 未注册名原样返回


def test_check_interactions_uses_aliases() -> None:
    # 别名也能命中 DDI 表（归一化后匹配）。
    agent = MedicationAgent()
    hits = agent.check_interactions(["拜阿司匹灵", "华法令"])
    assert len(hits) == 1
    assert hits[0].a == "华法林"
    assert hits[0].b == "阿司匹林"
