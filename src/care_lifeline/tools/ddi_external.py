"""外部药物相互作用数据源：openFDA 药品标签（Drug Label）API。

原理：若 A 药的 FDA 标签 ``drug_interactions`` 一节提及 B 药，即视为存在
相互作用记录（NLM RxNav 的 interaction 端点已于 2024-01 下线，openFDA
免费无 Key，是可行的实时替代）。启用 ``external_ddi_enabled`` 后，
DrugInteractionTool 在本地 DDI 表之外查询 openFDA 并按药品对合并
（外部数据优先）；任何网络/解析失败都降级为仅本地结果，保证 mock/离线
环境与 CI 完全不受影响。
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Any

import httpx

from care_lifeline.config import get_settings
from care_lifeline.tools.medication import DrugInteraction, MedicationAgent

logger = logging.getLogger(__name__)

# 中文规范名 → 英文通用名（openFDA 检索用）。未收录的药品直接跳过外部
# 查询（本地表仍兜底），不做机器翻译避免查错药。
_CN_TO_EN_DRUGS: dict[str, str] = {
    "华法林": "warfarin",
    "阿司匹林": "aspirin",
    "布洛芬": "ibuprofen",
    "胺碘酮": "amiodarone",
    "甲硝唑": "metronidazole",
    "利福平": "rifampin",
    "二甲双胍": "metformin",
    "螺内酯": "spironolactone",
    "地高辛": "digoxin",
    "辛伐他汀": "simvastatin",
    "阿托伐他汀": "atorvastatin",
    "氯吡格雷": "clopidogrel",
    "奥美拉唑": "omeprazole",
    "环孢素": "cyclosporine",
    "碳酸锂": "lithium carbonate",
    "对乙酰氨基酚": "acetaminophen",
    "氨氯地平": "amlodipine",
    "克拉霉素": "clarithromycin",
    "红霉素": "erythromycin",
    "伊曲康唑": "itraconazole",
    "氟康唑": "fluconazole",
    "甲氨蝶呤": "methotrexate",
    "苯妥英钠": "phenytoin",
    "非布司他": "febuxostat",
    "替罗非班": "tirofiban",
}

# 单次查询最多检查的药品对数，约束外部 API 调用次数与延迟。
_MAX_PAIRS = 6
# 相互作用描述文本的截断长度（写入 ToolResult.note）。
_NOTE_MAX_CHARS = 240
# severity 启发式关键词：标签文本含禁用/严重风险词时归为 major。
_MAJOR_KEYWORDS = ("contraindicated", "life-threatening", "serious", "severe")


def to_english_name(name_cn: str) -> str | None:
    """中文药名 → openFDA 检索英文通用名；先做别名归一化，未收录返回 ``None``。"""
    return _CN_TO_EN_DRUGS.get(MedicationAgent.normalize(name_cn))


def classify_severity(note: str) -> str:
    """按标签文本启发式判定严重程度；不确定时保守记为 ``moderate``。

    openFDA 标签不带结构化 severity 字段，只能从描述文本推断；
    ``major`` 仅在文本出现明确的高危关键词时给出。
    """
    lowered = note.lower()
    if any(keyword in lowered for keyword in _MAJOR_KEYWORDS):
        return "major"
    return "moderate"


def parse_label_results(payload: dict[str, Any]) -> str | None:
    """从 openFDA ``label.json`` 响应取第一条非空 ``drug_interactions`` 文本。"""
    for result in payload.get("results", []):
        for text in result.get("drug_interactions", []):
            if text:
                return str(text)
    return None


class OpenFDAClient:
    """openFDA 标签 API 客户端：按药品对查询 ``drug_interactions`` 提及。

    Args:
        base_url: openFDA 根地址（可配置，便于测试/代理）。
        timeout: 单请求超时秒数。
    """

    def __init__(self, base_url: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def fetch_interactions(self, names: list[str]) -> list[DrugInteraction]:
        """查询这组药品两两之间的相互作用记录。

        未收录中文名的药品跳过；单对查询失败只丢该对（记结构化日志，
        不记药名以免健康信息入日志），其余照常返回。输出药名保持中文。
        """
        cn_to_en = {
            MedicationAgent.normalize(name): english
            for name in names
            if (english := to_english_name(name)) is not None
        }
        if len(cn_to_en) < 2:
            return []
        results: list[DrugInteraction] = []
        seen: set[frozenset[str]] = set()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for (name_a, en_a), (name_b, en_b) in combinations(cn_to_en.items(), 2):
                if len(seen) >= _MAX_PAIRS:
                    break
                try:
                    note = await self._fetch_pair_note(client, en_a, en_b)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "openfda_pair_query_failed", extra={"error_type": type(exc).__name__}
                    )
                    continue
                if note is None:
                    continue  # 标签未提及该配对：视为无记录，不视为错误
                key = frozenset((name_a, name_b))
                if key not in seen:
                    seen.add(key)
                    results.append(
                        DrugInteraction(
                            a=name_a,
                            b=name_b,
                            severity=classify_severity(note),
                            note=note[:_NOTE_MAX_CHARS],
                            source="openfda",
                        )
                    )
        return results

    async def _fetch_pair_note(
        self, client: httpx.AsyncClient, generic_a: str, generic_b: str
    ) -> str | None:
        """查 A 药标签的相互作用一节是否提及 B 药；返回匹配文本或 ``None``。

        openFDA 在无匹配结果时返回 404，这是"无记录"的正常语义而非错误。
        """
        response = await client.get(
            f"{self._base_url}/drug/label.json",
            params={
                "search": f"openfda.generic_name:{generic_a} AND drug_interactions:{generic_b}"
            },
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return parse_label_results(response.json())


def merge_interactions(
    local: list[DrugInteraction], external: list[DrugInteraction]
) -> list[DrugInteraction]:
    """按药品对合并本地与外部记录；同一对以外部（更新鲜）数据为准。"""
    merged: dict[frozenset[str], DrugInteraction] = {}
    for item in local:
        merged[frozenset((item.a, item.b))] = item
    for item in external:
        merged[frozenset((item.a, item.b))] = item
    return list(merged.values())


async def fetch_external_interactions(names: list[str]) -> list[DrugInteraction]:
    """外部 DDI 查询入口；未启用或任何失败都返回空列表（调用方降级本地结果）。"""
    settings = get_settings()
    if not settings.external_ddi_enabled:
        return []
    client = OpenFDAClient(settings.openfda_base_url, settings.openfda_timeout_seconds)
    try:
        return await client.fetch_interactions(names)
    except httpx.HTTPError as exc:
        logger.warning("openfda_unavailable", extra={"error_type": type(exc).__name__})
        return []
    except Exception as exc:  # 防御：外部 API 结构变化等意外错误同样降级，不中断主流程
        logger.warning("openfda_unexpected_error", extra={"error_type": type(exc).__name__})
        return []
