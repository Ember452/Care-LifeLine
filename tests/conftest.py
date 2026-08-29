"""测试全局隔离约定。"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_feedback_dataset(tmp_path, monkeypatch):
    """数据飞轮写入重定向到临时目录，防止测试污染真实评测数据集。"""
    monkeypatch.setenv("CARE_FEEDBACK_DATA_PATH", str(tmp_path / "feedback_cases.json"))
    yield
