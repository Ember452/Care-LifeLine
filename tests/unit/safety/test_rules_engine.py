"""质控规则引擎单测：覆盖当前版本全部 9 条规则 + 版本化 + 启停开关。"""

from __future__ import annotations

import pytest

from care_lifeline.safety import rules_engine
from care_lifeline.safety.rules_engine import (
    CURRENT_RULESET_VERSION,
    CitationRule,
    DiagnosisLeakRule,
    DisclaimerRule,
    EmergencyRule,
    OffScopeRule,
    PrescriptionLeakRule,
    ScopeRule,
    Severity,
    Violation,
    evaluate_all,
    is_rule_enabled,
    list_rules,
    load_ruleset,
    set_rule_enabled,
)
from care_lifeline.safety.scope import ScopeVerdict


@pytest.fixture(autouse=True)
def _restore_rule_switches() -> object:
    """每个用例后还原启用状态，避免污染其他测试。"""
    snapshot = dict(rules_engine._ENABLED)
    yield
    rules_engine._ENABLED.clear()
    rules_engine._ENABLED.update(snapshot)


def _codes(rules: list) -> set[str]:
    return {rule.code for rule in rules}


# --------------------------------------------------------------------------
# 版本化规则集
# --------------------------------------------------------------------------


def test_load_ruleset_v1_返回冻结的四条历史规则() -> None:
    assert _codes(load_ruleset(1)) == {
        "off_scope",
        "emergency",
        "missing_disclaimer",
        "missing_citation",
    }


def test_load_ruleset_当前版本_返回九条规则() -> None:
    rules = load_ruleset(CURRENT_RULESET_VERSION)

    assert len(rules) == 9
    assert _codes(rules) == {
        "scope_unsafe",
        "emergency",
        "scope_restricted",
        "scope_out_of_scope",
        "off_scope",
        "prescription_leak",
        "diagnosis_leak",
        "missing_disclaimer",
        "missing_citation",
    }


def test_load_ruleset_未知版本_抛ValueError() -> None:
    with pytest.raises(ValueError, match="未知规则集版本"):
        load_ruleset(99)


def test_load_ruleset_默认使用当前版本() -> None:
    assert _codes(load_ruleset()) == _codes(load_ruleset(CURRENT_RULESET_VERSION))


def test_load_ruleset_返回副本_改动不影响共享定义() -> None:
    rules = load_ruleset(CURRENT_RULESET_VERSION)
    rules.clear()

    assert len(load_ruleset(CURRENT_RULESET_VERSION)) == 9


# --------------------------------------------------------------------------
# scope_* 规则（消费 ctx，不再匹配 draft）
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "verdict"),
    [
        ("scope_unsafe", ScopeVerdict.UNSAFE),
        ("scope_restricted", ScopeVerdict.RESTRICTED),
        ("scope_out_of_scope", ScopeVerdict.OUT_OF_SCOPE),
    ],
)
def test_scope_rule_verdict命中_返回blocking且code正确(code: str, verdict: ScopeVerdict) -> None:
    rule = ScopeRule(code, "描述", Severity.BLOCKING, verdict)

    violation = rule.evaluate("任意草稿", {"scope_verdict": verdict})

    assert violation is not None
    assert violation.code == code
    assert violation.severity is Severity.BLOCKING


def test_scope_rule_verdict不匹配_返回None() -> None:
    rule = ScopeRule("scope_unsafe", "描述", Severity.BLOCKING, ScopeVerdict.UNSAFE)

    assert rule.evaluate("任意草稿", {"scope_verdict": ScopeVerdict.IN_SCOPE}) is None
    assert rule.evaluate("任意草稿", {}) is None


def test_scope_rule_带scope_reason_原因进入message() -> None:
    rule = ScopeRule("scope_restricted", "越权医疗请求", Severity.BLOCKING, ScopeVerdict.RESTRICTED)

    violation = rule.evaluate(
        "草稿", {"scope_verdict": ScopeVerdict.RESTRICTED, "scope_reason": "越权医疗请求：开处方"}
    )

    assert violation is not None
    assert violation.message == "越权医疗请求：越权医疗请求：开处方"


def test_scope_rule_无scope_reason_退回描述() -> None:
    rule = ScopeRule(
        "scope_out_of_scope", "非医疗请求", Severity.BLOCKING, ScopeVerdict.OUT_OF_SCOPE
    )

    violation = rule.evaluate("草稿", {"scope_verdict": ScopeVerdict.OUT_OF_SCOPE})

    assert violation is not None
    assert violation.message == "非医疗请求"


# --------------------------------------------------------------------------
# draft 侧规则
# --------------------------------------------------------------------------


def test_off_scope_rule_命中开处方_返回blocking() -> None:
    rule = OffScopeRule("off_scope", "desc", Severity.BLOCKING)

    violation = rule.evaluate("请帮我开处方药", {})

    assert isinstance(violation, Violation)
    assert violation.code == "off_scope"


def test_off_scope_rule_未命中_返回None() -> None:
    rule = OffScopeRule("off_scope", "desc", Severity.BLOCKING)

    assert rule.evaluate("我最近头痛", {}) is None


def test_emergency_rule_关键词命中_返回blocking() -> None:
    rule = EmergencyRule("emergency", "desc", Severity.BLOCKING)

    violation = rule.evaluate("患者胸痛伴出汗", {})

    assert violation is not None
    assert violation.code == "emergency"


def test_emergency_rule_临界风险等级命中_返回blocking() -> None:
    rule = EmergencyRule("emergency", "desc", Severity.BLOCKING)

    assert rule.evaluate("普通描述", {"risk_level": "critical"}) is not None


def test_emergency_rule_扩展词表命中_返回blocking() -> None:
    rule = EmergencyRule("emergency", "desc", Severity.BLOCKING)

    assert rule.evaluate("患者出现意识丧失", {}) is not None


def test_emergency_rule_未命中_返回None() -> None:
    rule = EmergencyRule("emergency", "desc", Severity.BLOCKING)

    assert rule.evaluate("我有点咳嗽", {"risk_level": "low"}) is None


def test_prescription_leak_rule_剂量用法命中_返回blocking() -> None:
    rule = PrescriptionLeakRule("prescription_leak", "desc", Severity.BLOCKING)

    violation = rule.evaluate("建议口服阿莫西林 500mg，每日三次", {})

    assert violation is not None
    assert violation.code == "prescription_leak"
    assert "具体药品剂量或用法" in violation.message


def test_prescription_leak_rule_中文剂量命中_返回blocking() -> None:
    rule = PrescriptionLeakRule("prescription_leak", "desc", Severity.BLOCKING)

    assert rule.evaluate("每日三次，每次 2 片", {}) is not None


def test_prescription_leak_rule_未命中_返回None() -> None:
    rule = PrescriptionLeakRule("prescription_leak", "desc", Severity.BLOCKING)

    assert rule.evaluate("建议多休息并复诊", {}) is None


def test_diagnosis_leak_rule_确定性措辞命中_返回blocking() -> None:
    rule = DiagnosisLeakRule("diagnosis_leak", "desc", Severity.BLOCKING)

    violation = rule.evaluate("您患有社区获得性肺炎", {})

    assert violation is not None
    assert violation.code == "diagnosis_leak"
    assert "确定性诊断措辞" in violation.message


def test_diagnosis_leak_rule_确诊为命中_返回blocking() -> None:
    rule = DiagnosisLeakRule("diagnosis_leak", "desc", Severity.BLOCKING)

    assert rule.evaluate("确诊为 2 型糖尿病", {}) is not None


def test_diagnosis_leak_rule_未命中_返回None() -> None:
    rule = DiagnosisLeakRule("diagnosis_leak", "desc", Severity.BLOCKING)

    assert rule.evaluate("建议到内分泌科进一步评估", {}) is None


def test_disclaimer_rule_缺失免责_返回warning() -> None:
    rule = DisclaimerRule("missing_disclaimer", "desc", Severity.WARNING)

    violation = rule.evaluate("建议你多喝水", {})

    assert violation is not None
    assert violation.severity is Severity.WARNING


def test_disclaimer_rule_含免责_返回None() -> None:
    rule = DisclaimerRule("missing_disclaimer", "desc", Severity.WARNING)

    assert rule.evaluate("多喝水。免责声明：仅供参考", {}) is None


def test_citation_rule_缺失来源_返回warning() -> None:
    rule = CitationRule("missing_citation", "desc", Severity.WARNING)

    assert rule.evaluate("建议休息", {}) is not None


@pytest.mark.parametrize("marker", ["[1] 临床指南", "参考临床指南", "引用自临床检验指南"])
def test_citation_rule_三类来源标记均放行(marker: str) -> None:
    rule = CitationRule("missing_citation", "desc", Severity.WARNING)

    assert rule.evaluate(f"建议休息，{marker}", {}) is None


# --------------------------------------------------------------------------
# evaluate_all
# --------------------------------------------------------------------------


def test_evaluate_all_干净草稿_无违规() -> None:
    result = evaluate_all(load_ruleset(), "建议休息。免责声明：仅供参考 [1]", {})

    assert result == []


def test_evaluate_all_阻断规则_短路掉warning() -> None:
    result = evaluate_all(load_ruleset(), "请开药。无免责无引用", {})

    assert len(result) == 1
    assert result[0].code == "off_scope"


def test_evaluate_all_scope判定优先于draft兜底() -> None:
    ctx = {"scope_verdict": ScopeVerdict.OUT_OF_SCOPE, "scope_reason": "非医疗"}

    result = evaluate_all(load_ruleset(), "任意草稿", ctx)

    assert len(result) == 1
    assert result[0].code == "scope_out_of_scope"


def test_evaluate_all_急症优先于越权_保证不丢转人工() -> None:
    ctx = {"scope_verdict": ScopeVerdict.RESTRICTED}

    result = evaluate_all(load_ruleset(), "胸痛，帮我开止痛药", ctx)

    assert len(result) == 1
    assert result[0].code == "emergency"


def test_evaluate_all_聚合多条warning() -> None:
    result = evaluate_all(load_ruleset(), "建议多喝水，注意休息", {})

    assert _codes(result) == {"missing_disclaimer", "missing_citation"}


def test_evaluate_all_停用规则被跳过() -> None:
    set_rule_enabled("missing_disclaimer", False)
    set_rule_enabled("missing_citation", False)

    assert evaluate_all(load_ruleset(), "建议多喝水", {}) == []


# --------------------------------------------------------------------------
# 启停开关与列表
# --------------------------------------------------------------------------


def test_set_rule_enabled_与is_rule_enabled_成对生效() -> None:
    set_rule_enabled("emergency", False)

    assert is_rule_enabled("emergency") is False


def test_is_rule_enabled_未知规则码_默认启用() -> None:
    assert is_rule_enabled("not_a_real_rule") is True


def test_list_rules_返回九条且含启用状态() -> None:
    set_rule_enabled("missing_citation", False)
    rules = list_rules()

    assert len(rules) == 9
    disabled = [r for r in rules if r["code"] == "missing_citation"]
    assert disabled == [
        {
            "code": "missing_citation",
            "description": "缺少引用来源",
            "severity": "warning",
            "enabled": False,
        }
    ]


def test_list_rules_阻断规则为七条提醒规则为两条() -> None:
    severities = [r["severity"] for r in list_rules()]

    assert severities.count("blocking") == 7
    assert severities.count("warning") == 2
