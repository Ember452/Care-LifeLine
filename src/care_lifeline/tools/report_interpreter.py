from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod

from care_lifeline.graph.state import Citation, ReportField, ReportResult
from care_lifeline.tools.rag.reranker import Reranker
from care_lifeline.tools.rag.retriever import Retriever

logger = logging.getLogger(__name__)


class ReportInterpreter(ABC):
    """Turn free-text medical reports into structured, citation-grounded fields."""

    @abstractmethod
    def interpret(
        self, text: str, retriever: Retriever | None = None, reranker: Reranker | None = None
    ) -> ReportResult: ...


# 无检索器时的占位引用来源——不计入「忠实引用」（faithfulness 口径收紧用）。
PLACEHOLDER_SOURCES: tuple[str, ...] = ("临床检验指南", "指南")


def citation_has_real_source(citation: object) -> bool:
    """判断一条引用是否携带真实来源（faithfulness 严格口径）。

    引用必须含非空的 ``source`` 且不能是占位来源，才算「忠实引用」；
    用于评测套件与管理后台指标，防止 ``[``/``参考``/``引用`` 恒为 1.0 的假指标。

    Args:
        citation: ``Citation`` 实例或 ``{"source": ...}`` dict。

    Returns:
        是否携带真实来源。
    """
    source = getattr(citation, "source", None)
    if source is None and isinstance(citation, dict):
        source = citation.get("source")
    return isinstance(source, str) and bool(source) and source not in PLACEHOLDER_SOURCES


class MockReportInterpreter(ReportInterpreter):
    """Deterministic, offline extraction for tests/mock mode."""

    # 一行文本内的指标分隔符（P1-11：一行多指标，如「血压：150/95…，空腹血糖：7.8…」）。
    _SEGMENT_SEP = re.compile(r"[，,；;]")

    def interpret(
        self, text: str, retriever: Retriever | None = None, reranker: Reranker | None = None
    ) -> ReportResult:
        return ReportResult(
            fields=self._extract(text), citations=self._citations(text, retriever, reranker)
        )

    def _extract(self, text: str) -> list[ReportField]:
        fields: list[ReportField] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            for segment in self._SEGMENT_SEP.split(line):
                segment = segment.strip()
                if not segment:
                    continue
                name, sep, value = self._split(segment)
                if not sep or not name:
                    continue
                reference = self._reference(value)
                abnormal = any(
                    k in value for k in ("偏高", "偏低", "异常", "阳性", "升高", "降低", "超标")
                )
                fields.append(
                    ReportField(
                        name=name, value=value.strip(), reference=reference, abnormal=abnormal
                    )
                )
        return fields

    @staticmethod
    def _split(line: str) -> tuple[str, str, str]:
        for sep in ("：", ":"):
            if sep in line:
                name, _, value = line.partition(sep)
                return name.strip(), sep, value
        return line, "", ""

    @staticmethod
    def _reference(value: str) -> str | None:
        match = re.search(r"[（(]([^）)]*)[）)]", value)
        if not match:
            return None
        ref = match.group(1)
        if ref.startswith("参考范围"):
            ref = ref[4:]
        elif ref.startswith("参考"):
            ref = ref[2:]
        return ref.strip(" :：") or None

    def _citations(
        self, text: str, retriever: Retriever | None, reranker: Reranker | None
    ) -> list[Citation]:
        if retriever is None:
            return [
                Citation(
                    index=0,
                    source="临床检验指南",
                    snippet="请结合参考范围由医生综合病史评估，本报告解读仅供参考。",
                )
            ]
        chunks = retriever.retrieve(text, k=3)
        if reranker is not None:
            chunks = reranker.rerank(text, chunks)
        return [
            Citation(index=i, source=chunk.source or "指南", snippet=chunk.text[:80])
            for i, chunk in enumerate(chunks)
        ]


class LLMReportInterpreter(ReportInterpreter):
    """Real extraction via the configured LLM provider, with mock fallback."""

    def __init__(self, provider) -> None:
        self._provider = provider

    def interpret(
        self, text: str, retriever: Retriever | None = None, reranker: Reranker | None = None
    ) -> ReportResult:
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是报告解读助手。严格只输出 JSON："
                    '{"fields":[{"name":str,"value":str,"reference":str|null,"abnormal":bool}]}'
                ),
            },
            {"role": "user", "content": text},
        ]
        try:
            data = json.loads(self._provider.complete(messages=prompt))
            fields = [ReportField(**item) for item in data.get("fields", [])]
        except (json.JSONDecodeError, TypeError, ValueError):
            # 不吞异常：记录后再降级到确定性解析，避免静默失败难排查（P2-H）。
            logger.warning(
                "report_interpreter_llm_parse_failed",
                extra={"error_type": "json_parse", "text_length": len(text)},
            )
            return MockReportInterpreter().interpret(text, retriever, reranker)
        citations = MockReportInterpreter()._citations(text, retriever, reranker)
        return ReportResult(fields=fields, citations=citations)
