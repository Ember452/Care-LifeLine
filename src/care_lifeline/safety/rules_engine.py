"""质控规则引擎：版本化规则集 + 短路求值。

v1 为冻结的历史规则集（保持旧调用方行为不变）；v2 是当前规则集，按全量重构
契约 §2.4 改造：越界判定从「在 draft 里找黑名单词」改为「消费上游 scope 判定结果
``ctx["scope_verdict"]``」，并新增 ``prescription_leak`` / ``diagnosis_leak``
防模型绕过。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Protocol

from care_lifeline.safety.keywords import (
    CITATION_MARKERS,
    DIAGNOSIS_LEAK_PATTERNS,
    EMERGENCY_KEYWORDS,
    LEGACY_OFF_SCOPE_KEYWORDS,
    PRESCRIPTION_LEAK_PATTERNS,
)
from care_lifeline.safety.scope import ScopeVerdict

CURRENT_RULESET_VERSION = 2


class Severity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass
class Violation:
    code: str
    severity: Severity
    message: str


class QualityRule(Protocol):
    code: str
    severity: Severity

    def evaluate(self, draft: str, ctx: dict[str, object]) -> Violation | None: ...


@dataclass
class Rule(QualityRule):
    code: str
    description: str
    severity: Severity


@dataclass
class ScopeRule(Rule):
    """消费上游 scope 判定结果的阻断规则（契约 §2.4）。

    ``ctx["scope_verdict"]`` 与 :attr:`verdict` 相等即命中，阻断原因优先取
    ``ctx["scope_reason"]``，便于把判定依据带进审计与 SSE。
    """

    verdict: ScopeVerdict

    def evaluate(self, draft: str, ctx: dict[str, object]) -> Violation | None:
        if ctx.get("scope_verdict") != self.verdict:
            return None
        reason = ctx.get("scope_reason")
        message = f"{self.description}：{reason}" if isinstance(reason, str) else self.description
        return Violation(self.code, self.severity, message)


class OffScopeRule(Rule):
    """draft 侧的越界兜底（防御模型绕过输入侧判定）。"""

    keywords: ClassVar[tuple[str, ...]] = LEGACY_OFF_SCOPE_KEYWORDS

    def evaluate(self, draft: str, ctx: dict[str, object]) -> Violation | None:
        if any(keyword in draft for keyword in self.keywords):
            return Violation(self.code, self.severity, "检测到越界请求（开处方/开药），已拒答")
        return None


class EmergencyRule(Rule):
    keywords: ClassVar[tuple[str, ...]] = EMERGENCY_KEYWORDS

    def evaluate(self, draft: str, ctx: dict[str, object]) -> Violation | None:
        if ctx.get("risk_level") == "critical" or any(k in draft for k in self.keywords):
            return Violation(self.code, self.severity, "检测到高危症状，已转人工")
        return None


class PatternLeakRule(Rule):
    """按正则匹配 draft 的通用泄漏检测基类。"""

    patterns: ClassVar[tuple[str, ...]] = ()
    leak_label: ClassVar[str] = "越界内容"

    def evaluate(self, draft: str, ctx: dict[str, object]) -> Violation | None:
        matched = next((p for p in self.patterns if re.search(p, draft, re.IGNORECASE)), None)
        if matched is None:
            return None
        return Violation(self.code, self.severity, f"回复中出现{self.leak_label}，已拒答")


class PrescriptionLeakRule(PatternLeakRule):
    """回复中出现具体药品剂量/用法（防模型绕过输入侧的开处方拦截）。"""

    patterns: ClassVar[tuple[str, ...]] = PRESCRIPTION_LEAK_PATTERNS
    leak_label: ClassVar[str] = "具体药品剂量或用法"


class DiagnosisLeakRule(PatternLeakRule):
    """回复中出现确定性诊断措辞。"""

    patterns: ClassVar[tuple[str, ...]] = DIAGNOSIS_LEAK_PATTERNS
    leak_label: ClassVar[str] = "确定性诊断措辞"


class DisclaimerRule(Rule):
    def evaluate(self, draft: str, ctx: dict[str, object]) -> Violation | None:
        if "免责" not in draft:
            return Violation(self.code, self.severity, "回复缺少免责声明")
        return None


class CitationRule(Rule):
    def evaluate(self, draft: str, ctx: dict[str, object]) -> Violation | None:
        if not any(marker in draft for marker in CITATION_MARKERS):
            return Violation(self.code, self.severity, "回复缺少引用来源")
        return None


def _rule_defs(version: int = CURRENT_RULESET_VERSION) -> list[Rule]:
    """返回指定版本的规则定义。

    Args:
        version: 规则集版本号；``1`` 为冻结的历史版本，``2`` 为当前版本。

    Returns:
        按短路优先级排序的规则列表。

    Raises:
        ValueError: 版本号不存在。
    """
    if version == 1:
        return [
            OffScopeRule("off_scope", "越界请求拒答", Severity.BLOCKING),
            EmergencyRule("emergency", "高危症状转人工", Severity.BLOCKING),
            DisclaimerRule("missing_disclaimer", "缺少免责声明", Severity.WARNING),
            CitationRule("missing_citation", "缺少引用来源", Severity.WARNING),
        ]
    if version == 2:
        # 顺序即优先级：安全 > 急症转人工 > 越权 > 非医疗 > draft 侧兜底 > 提醒项。
        return [
            ScopeRule("scope_unsafe", "涉及自伤或违法内容", Severity.BLOCKING, ScopeVerdict.UNSAFE),
            EmergencyRule("emergency", "高危症状转人工", Severity.BLOCKING),
            ScopeRule(
                "scope_restricted", "越权医疗请求", Severity.BLOCKING, ScopeVerdict.RESTRICTED
            ),
            ScopeRule(
                "scope_out_of_scope", "非医疗请求", Severity.BLOCKING, ScopeVerdict.OUT_OF_SCOPE
            ),
            OffScopeRule("off_scope", "越界请求拒答", Severity.BLOCKING),
            PrescriptionLeakRule("prescription_leak", "处方级内容泄漏", Severity.BLOCKING),
            DiagnosisLeakRule("diagnosis_leak", "确定性诊断泄漏", Severity.BLOCKING),
            DisclaimerRule("missing_disclaimer", "缺少免责声明", Severity.WARNING),
            CitationRule("missing_citation", "缺少引用来源", Severity.WARNING),
        ]
    raise ValueError(f"未知规则集版本: {version}")


def load_ruleset(version: int = CURRENT_RULESET_VERSION) -> list[QualityRule]:
    """加载指定版本的规则集（返回副本，避免调用方改动共享定义）。

    Raises:
        ValueError: 版本号不存在。
    """
    return list(_rule_defs(version))


def evaluate_all(rules: list[QualityRule], draft: str, ctx: dict[str, object]) -> list[Violation]:
    """按序求值所有启用规则；命中阻断规则立即短路返回该条。

    Args:
        rules: 待执行的规则列表。
        draft: 待检文本（含用户输入与模型草稿）。
        ctx: 规则上下文，如 ``risk_level`` / ``scope_verdict`` / ``scope_reason``。

    Returns:
        违规列表；最多含一条 BLOCKING（短路），或若干条 WARNING。
    """
    violations: list[Violation] = []
    for rule in rules:
        if not is_rule_enabled(rule.code):
            continue
        violation = rule.evaluate(draft, ctx)
        if violation is None:
            continue
        if violation.severity == Severity.BLOCKING:
            return [violation]
        violations.append(violation)
    return violations


_ENABLED: dict[str, bool] = {rule.code: True for rule in _rule_defs(CURRENT_RULESET_VERSION)}


def set_rule_enabled(code: str, enabled: bool) -> None:
    """启用/停用单条规则（管理后台调用，变更需写审计）。"""
    _ENABLED[code] = enabled


def is_rule_enabled(code: str) -> bool:
    """返回规则是否启用；未知规则码默认启用。"""
    return _ENABLED.get(code, True)


def list_rules() -> list[dict]:
    """列出当前版本全部规则及其描述、级别与启用状态。"""
    return [
        {
            "code": rule.code,
            "description": rule.description,
            "severity": rule.severity.value,
            "enabled": is_rule_enabled(rule.code),
        }
        for rule in _rule_defs(CURRENT_RULESET_VERSION)
    ]
