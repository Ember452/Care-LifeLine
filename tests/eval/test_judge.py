"""有据率裁判（eval/judge.py）的行为测试。"""

from care_lifeline.eval.judge import LLMGroundednessJudge, MockGroundednessJudge
from care_lifeline.graph.state import Citation

_CITATIONS = [Citation(index=1, source="高血压管理指南", snippet="诊室血压 ≥140/90 可诊断")]


def test_mock_judge_supported_with_real_citation() -> None:
    judge = MockGroundednessJudge()
    assert judge.judge("血压偏高建议复诊", _CITATIONS) == 1.0


def test_mock_judge_rejects_placeholder_citation() -> None:
    judge = MockGroundednessJudge()
    placeholder = [Citation(index=1, source="指南", snippet="（引用自临床指南）")]
    assert judge.judge("血压偏高建议复诊", placeholder) == 0.0


def test_mock_judge_none_without_citations() -> None:
    assert MockGroundednessJudge().judge("普通回复", []) is None
    assert MockGroundednessJudge().judge("", _CITATIONS) is None


class _ScriptedProvider:
    """返回预设文本的桩 provider（供 LLM 裁判解析路径测试）。"""

    def __init__(self, raw: str) -> None:
        self._raw = raw
        self.prompts: list[str] = []

    def complete(
        self, *, messages: list[dict], temperature: float = 0.2, tier: str = "strong"
    ) -> str:
        self.prompts.append(str(messages))
        return self._raw

    def stream(self, **kwargs: object) -> object:
        yield ""

    def invoke_with_tools(self, **kwargs: object) -> object:
        raise NotImplementedError


def test_llm_judge_parses_supported_ratio() -> None:
    provider = _ScriptedProvider('{"supported_ratio": 0.8, "unsupported_claims": ["x"]}')
    judge = LLMGroundednessJudge(provider)  # type: ignore[arg-type]
    assert judge.judge("回复正文", _CITATIONS) == 0.8
    # prompt 里应包含草稿与引用渲染结果
    assert "回复正文" in provider.prompts[0]
    assert "高血压管理指南" in provider.prompts[0]


def test_llm_judge_clamps_ratio() -> None:
    provider = _ScriptedProvider('{"supported_ratio": 1.7, "unsupported_claims": []}')
    judge = LLMGroundednessJudge(provider)  # type: ignore[arg-type]
    assert judge.judge("回复正文", _CITATIONS) == 1.0
    provider2 = _ScriptedProvider('{"supported_ratio": -0.3, "unsupported_claims": []}')
    assert LLMGroundednessJudge(provider2).judge("回复正文", _CITATIONS) == 0.0  # type: ignore[arg-type]


def test_llm_judge_unparsable_returns_none() -> None:
    # 解析失败返回 None（用例不进指标），而不是记 0 分伪装成「无据」。
    judge = LLMGroundednessJudge(_ScriptedProvider("我觉得很不错"))  # type: ignore[arg-type]
    assert judge.judge("回复正文", _CITATIONS) is None
    judge2 = LLMGroundednessJudge(_ScriptedProvider('{"supported_ratio": "高"}'))  # type: ignore[arg-type]
    assert judge2.judge("回复正文", _CITATIONS) is None


def test_llm_judge_skips_empty_inputs() -> None:
    judge = LLMGroundednessJudge(_ScriptedProvider("{}"))  # type: ignore[arg-type]
    assert judge.judge("回复正文", []) is None
