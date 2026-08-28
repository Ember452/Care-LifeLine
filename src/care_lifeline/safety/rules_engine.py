from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Protocol


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

    def evaluate(self, draft: str, ctx: dict) -> Violation | None: ...


@dataclass
class Rule(QualityRule):
    code: str
    description: str
    severity: Severity


class OffScopeRule(Rule):
    keywords: ClassVar[tuple[str, ...]] = ("开处方", "开药", "诊断结论")

    def evaluate(self, draft: str, ctx: dict) -> Violation | None:
        if any(k in draft for k in self.keywords):
            return Violation(self.code, self.severity, "检测到越界请求（开处方/开药），已拒答")
        return None


EMERGENCY_KEYWORDS: tuple[str, ...] = ("胸痛", "呼吸困难", "卒中", "抽搐", "昏迷")


class EmergencyRule(Rule):
    keywords: ClassVar[tuple[str, ...]] = EMERGENCY_KEYWORDS

    def evaluate(self, draft: str, ctx: dict) -> Violation | None:
        is_critical = ctx.get("risk_level") == "critical"
        has_keyword = any(k in draft for k in self.keywords)
        if is_critical or has_keyword:
            return Violation(self.code, self.severity, "检测到高危症状，已转人工")
        return None


class DisclaimerRule(Rule):
    def evaluate(self, draft: str, ctx: dict) -> Violation | None:
        if "免责" not in draft:
            return Violation(self.code, self.severity, "回复缺少免责声明")
        return None


class CitationRule(Rule):
    def evaluate(self, draft: str, ctx: dict) -> Violation | None:
        has_citation = "[" in draft or "参考" in draft
        if not has_citation:
            return Violation(self.code, self.severity, "回复缺少引用来源")
        return None


def _rule_defs(version: int = 1) -> list[Rule]:
    if version == 1:
        return [
            OffScopeRule("off_scope", "越界请求拒答", Severity.BLOCKING),
            EmergencyRule("emergency", "高危症状转人工", Severity.BLOCKING),
            DisclaimerRule("missing_disclaimer", "缺少免责声明", Severity.WARNING),
            CitationRule("missing_citation", "缺少引用来源", Severity.WARNING),
        ]
    raise ValueError(f"未知规则集版本: {version}")


def load_ruleset(version: int = 1) -> list[QualityRule]:
    return list(_rule_defs(version))


def evaluate_all(rules: list[QualityRule], draft: str, ctx: dict) -> list[Violation]:
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


_ENABLED: dict[str, bool] = {rule.code: True for rule in _rule_defs(1)}


def set_rule_enabled(code: str, enabled: bool) -> None:
    _ENABLED[code] = enabled


def is_rule_enabled(code: str) -> bool:
    return _ENABLED.get(code, True)


def list_rules() -> list[dict]:
    return [
        {
            "code": rule.code,
            "description": rule.description,
            "severity": rule.severity.value,
            "enabled": is_rule_enabled(rule.code),
        }
        for rule in _rule_defs(1)
    ]
