"""外部 DDI 数据源（tools/ddi_external.py）的行为测试；全部离线，不连真实 API。"""


import httpx
import pytest

from care_lifeline.config import get_settings
from care_lifeline.tools import ddi_external, registry
from care_lifeline.tools.ddi_external import (
    OpenFDAClient,
    classify_severity,
    parse_label_results,
    to_english_name,
)
from care_lifeline.tools.medication import DrugInteraction


@pytest.fixture()
def enable_external_ddi(monkeypatch):
    monkeypatch.setenv("CARE_EXTERNAL_DDI_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_to_english_name_normalizes_alias_and_unknown() -> None:
    assert to_english_name("华法林") == "warfarin"
    assert to_english_name("拜阿司匹灵") == "aspirin"  # 别名先归一化再映射
    assert to_english_name("青霉素") is None  # 未收录：跳过外部查询，本地表兜底


def test_classify_severity_heuristic() -> None:
    assert classify_severity("This combination is CONTRAINDICATED in patients with...") == "major"
    assert classify_severity("May increase bleeding risk; monitor INR.") == "moderate"


def test_parse_label_results_takes_first_nonempty_text() -> None:
    payload = {"results": [{"drug_interactions": ["", "Warfarin may increase INR."]}, {}]}
    assert parse_label_results(payload) == "Warfarin may increase INR."
    assert parse_label_results({"results": []}) is None


async def test_fetch_disabled_returns_empty_by_default() -> None:
    assert await ddi_external.fetch_external_interactions(["华法林"]) == []


async def test_fetch_skips_unmapped_and_single_drug(enable_external_ddi) -> None:
    # 未收录药品 + 只有 1 个可映射药品：不发起外部请求，返回空
    assert await ddi_external.fetch_external_interactions(["青霉素", "阿司匹林"]) == []


async def test_client_404_means_no_interaction(enable_external_ddi) -> None:
    """openFDA 无匹配返回 404，是「无记录」语义而非错误：该对跳过、不降级整轮。"""

    class _NotFoundTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})

    client = OpenFDAClient("https://api.fda.gov", timeout=3.0)
    async with httpx.AsyncClient(transport=_NotFoundTransport()) as http_client:
        note = await client._fetch_pair_note(http_client, "aspirin", "metformin")
    assert note is None


async def test_client_parses_hit(enable_external_ddi) -> None:
    payload = {"results": [{"drug_interactions": ["Serious bleeding risk reported."]}]}
    calls: list[str] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=payload)

    class _HitTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return await _handler(request)

    client = OpenFDAClient("https://api.fda.gov", timeout=3.0)
    async with httpx.AsyncClient(transport=_HitTransport()) as http_client:
        note = await client._fetch_pair_note(http_client, "warfarin", "aspirin")
    assert note == "Serious bleeding risk reported."
    assert "drug/label.json" in calls[0]
    assert "warfarin" in calls[0] and "aspirin" in calls[0]


async def test_fetch_degrades_to_empty_on_network_error(monkeypatch, enable_external_ddi) -> None:
    async def _boom(self: OpenFDAClient, names: list[str]) -> list[DrugInteraction]:
        raise httpx.ConnectError("openfda unreachable")

    monkeypatch.setattr(OpenFDAClient, "fetch_interactions", _boom)
    assert await ddi_external.fetch_external_interactions(["华法林", "阿司匹林"]) == []


async def test_tool_merges_external_results(monkeypatch, enable_external_ddi) -> None:
    """工具集成：开关开启时本地 + 外部合并，外部同名对覆盖本地。"""

    async def _fake_fetch(names: list[str]) -> list[DrugInteraction]:
        assert "华法林" in names
        return [
            DrugInteraction(
                a="华法林", b="胺碘酮", severity="major", note="openFDA live", source="openfda"
            )
        ]

    monkeypatch.setattr(ddi_external, "fetch_external_interactions", _fake_fetch)
    result = await registry.DrugInteractionTool().run(drugs=["华法林", "胺碘酮"])
    assert result.ok is True
    interactions = result.data["interactions"]
    pair = next(i for i in interactions if {i["a"], i["b"]} == {"华法林", "胺碘酮"})
    assert pair["source"] == "openfda"  # 本地表同对记录被外部数据覆盖
    assert len([i for i in interactions if {i["a"], i["b"]} == {"华法林", "胺碘酮"}]) == 1


async def test_tool_without_switch_keeps_local_only() -> None:
    result = await registry.DrugInteractionTool().run(drugs=["华法林", "阿司匹林"])
    assert result.ok is True
    assert result.data["interactions"][0]["source"] == "offline"
