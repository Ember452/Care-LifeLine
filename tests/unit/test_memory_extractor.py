"""记忆变更提取器（memory/extractor.py）的行为测试。"""

from langchain_core.messages import HumanMessage  # noqa: F401  (占位：无)

from care_lifeline.memory.extractor import (
    ProposalDraft,
    extract_proposals,
    extract_proposals_regex,
)


def test_regex_extracts_medication_add() -> None:
    drafts = extract_proposals_regex("医生，我开始服用布洛芬了，关节疼好多了。")
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.kind == "medication"
    assert draft.action == "add"
    assert draft.payload["name"] == "布洛芬"
    assert "布洛芬" in draft.excerpt  # 摘自对话原句


def test_regex_extracts_medication_stop_and_allergy() -> None:
    drafts = extract_proposals_regex("我把阿司匹林停用了。另外我对青霉素过敏。")
    kinds = {(d.kind, d.action, d.payload.get("name") or d.payload.get("allergen")) for d in drafts}
    assert ("medication", "stop", "阿司匹林") in kinds
    assert ("allergy", "add", "青霉素") in kinds


def test_regex_dedupes_same_proposal() -> None:
    drafts = extract_proposals_regex("我开始服用布洛芬了，一直在吃布洛芬。")
    meds = [d for d in drafts if d.kind == "medication" and d.action == "add"]
    assert len(meds) == 1


def test_regex_no_false_positive_on_plain_text() -> None:
    assert extract_proposals_regex("最近血压有点高，需要注意什么？") == []


def test_extract_empty_text() -> None:
    assert extract_proposals("   ") == []


class _LLMExtractorProvider:
    """返回预设 JSON 数组的桩 provider（real 模式抽取路径）。"""

    def __init__(self, raw: str) -> None:
        self._raw = raw

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: str = "strong"
    ) -> str:
        return self._raw

    def stream(self, **kwargs: object) -> object:
        yield ""

    def invoke_with_tools(self, **kwargs: object) -> object:
        raise NotImplementedError


def test_llm_extraction_parses_and_validates(monkeypatch) -> None:
    monkeypatch.setenv("CARE_LLM_MODE", "real")
    from care_lifeline.config import get_settings

    get_settings.cache_clear()
    try:
        raw = (
            '[{"kind": "medication", "action": "add", "name": "二甲双胍",'
            ' "excerpt": "在吃二甲双胍"}, {"kind": "bogus", "name": "x"}]'
        )
        provider = _LLMExtractorProvider(raw)
        drafts = extract_proposals("我在吃二甲双胍", provider)  # type: ignore[arg-type]
        assert len(drafts) == 1  # 非法 kind 被过滤
        assert drafts[0].payload["name"] == "二甲双胍"
    finally:
        get_settings.cache_clear()


def test_llm_unparsable_falls_back_to_regex(monkeypatch) -> None:
    monkeypatch.setenv("CARE_LLM_MODE", "real")
    from care_lifeline.config import get_settings

    get_settings.cache_clear()
    try:
        provider = _LLMExtractorProvider("我觉得没什么要记的")
        drafts = extract_proposals("我开始服用阿司匹林了", provider)  # type: ignore[arg-type]
        assert len(drafts) == 1
        assert drafts[0].payload["name"] == "阿司匹林"
    finally:
        get_settings.cache_clear()


def test_mock_mode_uses_regex_only() -> None:
    # mock 模式即使 provider 缺失也走正则：零外部依赖可回归
    drafts = extract_proposals("我对青霉素过敏", provider=None)
    assert len(drafts) == 1
    assert drafts[0].kind == "allergy"


def test_proposal_draft_dedupe_key() -> None:
    a = ProposalDraft(kind="medication", action="add", payload={"name": "布洛芬"})
    b = ProposalDraft(kind="medication", action="add", payload={"name": "布洛芬", "dosage": "0.2g"})
    assert a.dedupe_key == b.dedupe_key
