from __future__ import annotations

from care_lifeline.safety.rules_engine import (
    CitationRule,
    DisclaimerRule,
    EmergencyRule,
    OffScopeRule,
    Severity,
    Violation,
    evaluate_all,
    load_ruleset,
)


def test_load_ruleset_v1_returns_four_rules() -> None:
    rules = load_ruleset(1)
    codes = {r.code for r in rules}
    assert codes == {"off_scope", "emergency", "missing_disclaimer", "missing_citation"}


def test_load_ruleset_unknown_version_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        load_ruleset(99)


def test_off_scope_rule_miss_returns_none() -> None:
    rule = OffScopeRule("off_scope", "desc", Severity.BLOCKING)
    assert rule.evaluate("我最近头痛", {}) is None


def test_off_scope_rule_hit_returns_blocking() -> None:
    rule = OffScopeRule("off_scope", "desc", Severity.BLOCKING)
    v = rule.evaluate("请帮我开处方药", {})
    assert isinstance(v, Violation)
    assert v.severity is Severity.BLOCKING
    assert v.code == "off_scope"


def test_emergency_rule_hit_keyword_returns_blocking() -> None:
    rule = EmergencyRule("emergency", "desc", Severity.BLOCKING)
    v = rule.evaluate("患者胸痛伴出汗", {})
    assert v is not None and v.severity is Severity.BLOCKING and v.code == "emergency"


def test_emergency_rule_hit_critical_ctx_returns_blocking() -> None:
    rule = EmergencyRule("emergency", "desc", Severity.BLOCKING)
    v = rule.evaluate("普通描述", {"risk_level": "critical"})
    assert v is not None and v.code == "emergency"


def test_emergency_rule_miss_returns_none() -> None:
    rule = EmergencyRule("emergency", "desc", Severity.BLOCKING)
    assert rule.evaluate("我有点咳嗽", {"risk_level": "low"}) is None


def test_disclaimer_rule_miss_returns_warning() -> None:
    rule = DisclaimerRule("missing_disclaimer", "desc", Severity.WARNING)
    v = rule.evaluate("建议你多喝水", {})
    assert v is not None and v.severity is Severity.WARNING and v.code == "missing_disclaimer"


def test_disclaimer_rule_hit_returns_none() -> None:
    rule = DisclaimerRule("missing_disclaimer", "desc", Severity.WARNING)
    assert rule.evaluate("多喝水。免责声明：仅供参考", {}) is None


def test_citation_rule_miss_returns_warning() -> None:
    rule = CitationRule("missing_citation", "desc", Severity.WARNING)
    v = rule.evaluate("建议休息", {})
    assert v is not None and v.code == "missing_citation"


def test_citation_rule_hit_bracket_returns_none() -> None:
    rule = CitationRule("missing_citation", "desc", Severity.WARNING)
    assert rule.evaluate("参考指南 [1]", {}) is None


def test_evaluate_all_clean_draft_no_violations() -> None:
    rules = load_ruleset(1)
    result = evaluate_all(rules, "建议休息。免责声明：仅供参考 [1]", {})
    assert result == []


def test_evaluate_all_blocking_short_circuits_warnings() -> None:
    rules = load_ruleset(1)
    result = evaluate_all(rules, "请开药。无免责无引用", {})
    assert len(result) == 1
    assert result[0].code == "off_scope"


def test_evaluate_all_aggregates_warnings() -> None:
    rules = load_ruleset(1)
    result = evaluate_all(rules, "建议多喝水，注意休息", {})
    codes = {v.code for v in result}
    assert codes == {"missing_disclaimer", "missing_citation"}


def test_evaluate_all_emergency_short_circuits() -> None:
    rules = load_ruleset(1)
    result = evaluate_all(rules, "患者胸痛，没有免责", {})
    assert len(result) == 1
    assert result[0].code == "emergency"
