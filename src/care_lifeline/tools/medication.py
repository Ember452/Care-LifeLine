from __future__ import annotations

import re

from pydantic import BaseModel


class DrugInteraction(BaseModel):
    a: str
    b: str
    severity: str  # contraindicated | major | moderate | minor
    note: str
    source: str = "offline"  # offline=本地 DDI 表；rxnav=NLM RxNav 实时查询


# 药品名归一化：别名/商品名 → 规范名（检索 DDI 表前先归一）。
_ALIAS_MAP: dict[str, str] = {
    "拜阿司匹灵": "阿司匹林",
    "阿斯匹林": "阿司匹林",
    "阿司匹灵": "阿司匹林",
    "华法令": "华法林",
    "芬必得": "布洛芬",
    "格华止": "二甲双胍",
    "普乐安": "二甲双胍",
    "络活喜": "氨氯地平",
    "欣维宁": "替罗非班",
    "波立维": "氯吡格雷",
    "立普妥": "阿托伐他汀",
    "可定": "瑞舒伐他汀",
    "舒降之": "辛伐他汀",
    "地高辛": "地高辛",
    "环孢素": "环孢素",
    "立维宁": "甲氨蝶呤",
    "泰诺": "对乙酰氨基酚",
    "必理通": "对乙酰氨基酚",
    "诺氟沙星": "诺氟沙星",
    "红霉素": "红霉素",
    "克拉霉素": "克拉霉素",
    "伊曲康唑": "伊曲康唑",
    "氟康唑": "氟康唑",
    "利福平": "利福平",
    "苯妥英钠": "苯妥英钠",
    "碳酸锂": "碳酸锂",
    "胺碘酮": "胺碘酮",
    "华法林钠": "华法林",
    "非布司他": "非布司他",
}


# 离线 DDI 知识库（≥20 条，供演示与 CI 回归）。生产环境应替换为 RxNorm + FDA
# 实时接口；此处为无外部依赖的可测试基线。
_DDI_TABLE: list[DrugInteraction] = [
    DrugInteraction(
        a="华法林", b="阿司匹林", severity="major", note="合用显著增加出血风险，需监测 INR。"
    ),
    DrugInteraction(a="华法林", b="布洛芬", severity="major", note="NSAIDs 增加胃肠道出血风险。"),
    DrugInteraction(
        a="华法林", b="胺碘酮", severity="major", note="胺碘酮抑制华法林代谢，显著升高 INR。"
    ),
    DrugInteraction(
        a="华法林", b="甲硝唑", severity="major", note="合用增强抗凝作用，增加出血风险。"
    ),
    DrugInteraction(
        a="华法林", b="利福平", severity="major", note="利福平诱导肝酶，削弱华法林抗凝疗效。"
    ),
    DrugInteraction(
        a="二甲双胍", b="酒精", severity="moderate", note="增加乳酸酸中毒与低血糖风险。"
    ),
    DrugInteraction(
        a="二甲双胍", b="碘造影剂", severity="major", note="急性肾损伤患者合用可诱发乳酸酸中毒。"
    ),
    DrugInteraction(
        a="ACE抑制剂", b="螺内酯", severity="major", note="合用电解质紊乱（高钾）风险。"
    ),
    DrugInteraction(
        a="ACE抑制剂", b="钾补充剂", severity="moderate", note="增加高钾血症风险，需监测血钾。"
    ),
    DrugInteraction(a="西酞普兰", b="曲马多", severity="major", note="5-羟色胺综合征风险。"),
    DrugInteraction(a="他汀", b="红霉素", severity="moderate", note="增加肌病风险。"),
    DrugInteraction(
        a="他汀",
        b="克拉霉素",
        severity="major",
        note="CYP3A4 抑制使他汀暴露升高，增加横纹肌溶解风险。",
    ),
    DrugInteraction(
        a="他汀", b="伊曲康唑", severity="major", note="合用显著升高他汀血药浓度，谨防肌毒性。"
    ),
    DrugInteraction(
        a="阿托伐他汀", b="胺碘酮", severity="moderate", note="增加肌病与肝功能异常风险。"
    ),
    DrugInteraction(
        a="辛伐他汀", b="环孢素", severity="major", note="合用增加横纹肌溶解风险，避免联用。"
    ),
    DrugInteraction(
        a="地高辛", b="胺碘酮", severity="major", note="胺碘酮升高地高辛血药浓度，易致中毒。"
    ),
    DrugInteraction(
        a="地高辛", b="螺内酯", severity="moderate", note="减少地高辛清除，增加中毒风险。"
    ),
    DrugInteraction(
        a="氨氯地平", b="辛伐他汀", severity="moderate", note="合用辛伐他汀暴露升高，剂量需限制。"
    ),
    DrugInteraction(
        a="氯吡格雷",
        b="奥美拉唑",
        severity="moderate",
        note="CYP2C19 抑制降低氯吡格雷活化，抗血小板疗效下降。",
    ),
    DrugInteraction(
        a="甲氨蝶呤",
        b="非甾体抗炎药",
        severity="major",
        note="NSAIDs 减少甲氨蝶呤清除，增加骨髓抑制与肾毒性。",
    ),
    DrugInteraction(
        a="碳酸锂", b="噻嗪类利尿剂", severity="major", note="合用升高血锂浓度，易致锂中毒。"
    ),
    DrugInteraction(
        a="对乙酰氨基酚", b="酒精", severity="moderate", note="慢性饮酒者合用增加肝毒性风险。"
    ),
]


class MedicationAgent:
    """用药相互作用审查（P2）。离线知识库基线；生产可接 RxNorm/FDA。"""

    _SEP = re.compile(r"[\s,，、;；/]+")

    @classmethod
    def normalize(cls, drug: str) -> str:
        """药品名归一化：别名/商品名映射到规范名（原样返回未注册名）。"""
        stripped = drug.strip()
        return _ALIAS_MAP.get(stripped, stripped)

    def extract_drugs(self, text: str) -> list[str]:
        return [t for t in self._SEP.split(text) if t]

    def check_interactions(self, drugs: list[str]) -> list[DrugInteraction]:
        names = {self.normalize(d) for d in drugs if d.strip()}
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
