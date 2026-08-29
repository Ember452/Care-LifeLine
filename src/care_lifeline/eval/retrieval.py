"""检索质量评测：指南语料上的 hit@k 与 MRR（设计文档 §9.1 检索口径）。

用例在 ``data/eval/retrieval_cases.json``（查询 → 期望命中的指南文件），
与 RAG 语料目录隔离（评测集不进检索索引）。默认走当前配置的检索管线
（mock 向量 + BM25 混合 + rerank），配置 ``CARE_RAG_ENABLED``/
``CARE_QDRANT_URL`` 后同一份用例即可评测真实向量链路。
"""

from __future__ import annotations

from care_lifeline.eval.suite import _load
from care_lifeline.tools.rag.registry import build_report_retriever

RETRIEVAL_DATASET = "retrieval_cases"
RETRIEVAL_REPORT = "eval_retrieval.md"
_K = 3


def load_cases() -> list[dict]:
    return _load(RETRIEVAL_DATASET)


def hit_rank(reranked_sources: list[str], expect_source: str) -> int | None:
    """期望文件在 top 结果中的名次（1 起）；未命中返回 ``None``。"""
    for rank, source in enumerate(reranked_sources, start=1):
        if source == expect_source:
            return rank
    return None


def run_retrieval_eval(report_path: str = RETRIEVAL_REPORT) -> dict:
    """跑检索评测并输出 Markdown 报告。

    Returns:
        含 per_case 明细、hit_at_1 / hit_at_3 / mrr 指标与报告文本。
    """
    bundle = build_report_retriever()
    if bundle is None:
        report = "# 检索质量评测\n\n检索管线不可用（指南语料缺失或后端不可达）。\n"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        return {"cases": [], "hit_at_1": 0.0, "hit_at_3": 0.0, "mrr": 0.0, "report": report}

    retriever, reranker, _chunks = bundle
    details: list[dict] = []
    for case in load_cases():
        query = str(case.get("query", ""))
        expect = str(case.get("expect_source", ""))
        hits = reranker.rerank(query, retriever.retrieve(query, k=_K))
        sources = [c.source or "" for c in hits]
        rank = hit_rank(sources, expect)
        details.append(
            {
                "query": query,
                "expect": expect,
                "top_sources": sources,
                "rank": rank,
            }
        )

    total = len(details)
    hit_at_1 = sum(1 for d in details if d["rank"] == 1) / total if total else 0.0
    hit_at_3 = sum(1 for d in details if d["rank"] is not None) / total if total else 0.0
    mrr = (
        sum(1.0 / d["rank"] for d in details if d["rank"] is not None) / total if total else 0.0
    )
    report = render_markdown(details, hit_at_1, hit_at_3, mrr)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    return {
        "cases": details,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "mrr": mrr,
        "report": report,
    }


def render_markdown(details: list[dict], hit_at_1: float, hit_at_3: float, mrr: float) -> str:
    lines = [
        "# 指南检索质量评测（hit@k / MRR）",
        "",
        f"- 用例数：{len(details)}；top-k：{_K}",
        f"- hit@1：**{round(hit_at_1, 4)}**　hit@3：**{round(hit_at_3, 4)}**　"
        f"MRR：**{round(mrr, 4)}**",
        "",
        "| 查询 | 期望文件 | 命中名次 | top 来源 |",
        "|---|---|---|---|",
    ]
    for d in details:
        rank = d["rank"] if d["rank"] is not None else "未命中"
        lines.append(
            f"| {d['query']} | {d['expect']} | {rank} | {'、'.join(d['top_sources']) or '-'} |"
        )
    lines += [
        "",
        "> 用例与 RAG 语料隔离（data/eval 不进检索索引）；",
        "> 配置 CARE_RAG_ENABLED/CARE_QDRANT_URL 后可用同一份用例评测真实向量链路。",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    outcome = run_retrieval_eval()
    print(f"检索评测完成 -> {RETRIEVAL_REPORT}")
    print(f"  hit@1: {outcome['hit_at_1']}  hit@3: {outcome['hit_at_3']}  mrr: {outcome['mrr']}")
