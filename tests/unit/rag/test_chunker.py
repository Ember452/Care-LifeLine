from __future__ import annotations

from care_lifeline.tools.rag.chunker import chunk_text

GUIDELINE = """# 高血压管理指南

## 诊断标准
非同日三次测量收缩压 ≥ 140 mmHg 或舒张压 ≥ 90 mmHg 可诊断高血压。

## 目标值
一般患者血压目标 < 140/90 mmHg；合并糖尿病或肾病者 < 130/80 mmHg。

## 生活干预
建议低盐饮食、规律有氧运动、控制体重，并戒烟限酒。
"""


def test_chunk_splits_on_heading_and_paragraph() -> None:
    chunks = chunk_text(GUIDELINE, source="guide.md")
    sections = {c.section for c in chunks}
    assert "诊断标准" in sections
    assert "目标值" in sections
    assert "生活干预" in sections
    assert all(len(c.text) <= 500 for c in chunks)


def test_chunk_index_unique_and_ordered() -> None:
    chunks = chunk_text(GUIDELINE)
    indices = [c.index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_long_paragraph_is_split() -> None:
    long = "这是第一句。" * 100
    assert len(long) > 500
    chunks = chunk_text(long, max_chars=200)
    assert all(len(c.text) <= 200 for c in chunks)
    assert len(chunks) > 1


def test_empty_text_yields_no_chunks() -> None:
    assert chunk_text("   \n\n  ") == []
