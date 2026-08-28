from __future__ import annotations

import re

from pydantic import BaseModel


class DrugInteraction(BaseModel):
    a: str
    b: str
    severity: str  # contraindicated | major | moderate
    note: str


# 离线 DDI 知识库（示例子集）。生产环境应替换为 RxNorm + FDA 实时接口，
# 此处为无外部依赖的可测试基线。
_DDI_TABLE: list[DrugInteraction] = [
    DrugInteraction(
        a="华法林", b="阿司匹林", severity="major", note="合用显著增加出血风险，需监测 INR。"
    ),
    DrugInteraction(
        a="华法林", b="布洛芬", severity="major", note="NSAIDs 增加胃肠道出血风险。"
    ),
    DrugInteraction(
        a="二甲双胍", b="酒精", severity="moderate", note="增加乳酸酸中毒与低血糖风险。"
    ),
    DrugInteraction(
        a="ACE抑制剂", b="螺内酯", severity="major", note="合用电解质紊乱（高钾）风险。"
    ),
    DrugInteraction(
        a="西酞普兰", b="曲马多", severity="major", note="5-羟色胺综合征风险。"
    ),
    DrugInteraction(a="他汀", b="红霉素", severity="moderate", note="增加肌病风险。"),
]


class MedicationAgent:
    """用药相互作用审查（P2）。离线知识库基线；生产可接 RxNorm/FDA。"""

    _SEP = re.compile(r"[\s,，、;；/]+")

    def extract_drugs(self, text: str) -> list[str]:
        return [t for t in self._SEP.split(text) if t]

    def check_interactions(self, drugs: list[str]) -> list[DrugInteraction]:
        names = {d.strip() for d in drugs if d.strip()}
        found: list[DrugInteraction] = []
        for item in _DDI_TABLE:
            if item.a in names and item.b in names:
                found.append(item)
        return found

    def warnings(self, drugs: list[str]) -> list[str]:
        out: list[str] = []
        for hit in self.check_interactions(drugs):
            out.append(f"【{hit.severity}】{hit.a} + {hit.b}：{hit.note}")
        return out
