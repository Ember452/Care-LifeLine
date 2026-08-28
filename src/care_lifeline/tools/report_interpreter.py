from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from care_lifeline.graph.state import Citation, ReportField, ReportResult
from care_lifeline.tools.rag.reranker import Reranker
from care_lifeline.tools.rag.retriever import Retriever


class ReportInterpreter(ABC):
    """Turn free-text medical reports into structured, citation-grounded fields."""

    @abstractmethod
    def interpret(
        self, text: str, retriever: Retriever | None = None, reranker: Reranker | None = None
    ) -> ReportResult:
        ...


class MockReportInterpreter(ReportInterpreter):
    """Deterministic, offline extraction for tests/mock mode."""

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
            name, sep, value = self._split(line)
            if not sep or not name:
                continue
            reference = self._reference(value)
            abnormal = any(
                k in value for k in ("偏高", "偏低", "异常", "阳性", "升高", "降低", "超标")
            )
            fields.append(
                ReportField(name=name, value=value.strip(), reference=reference, abnormal=abnormal)
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
            return MockReportInterpreter().interpret(text, retriever, reranker)
        citations = MockReportInterpreter()._citations(text, retriever, reranker)
        return ReportResult(fields=fields, citations=citations)
