"""P1-E 测试隔离：每个用例前后清空 checkpointer 单例。

checkpointer 持有指向各用例临时 SQLite 的连接，若跨用例残留会把
checkpoint 写进上一用例的数据库、并让 interrupt 状态跨线程泄漏。
"""

from __future__ import annotations

import pytest

from care_lifeline.graph.checkpointer import reset_checkpointer_for_testing


@pytest.fixture(autouse=True)
def _reset_checkpointer():
    reset_checkpointer_for_testing()
    yield
    reset_checkpointer_for_testing()


@pytest.fixture(autouse=True)
def _isolate_feedback_dataset(tmp_path, monkeypatch):
    """数据飞轮写入重定向到临时目录，防止测试污染真实评测数据集。"""
    monkeypatch.setenv("CARE_FEEDBACK_DATA_PATH", str(tmp_path / "feedback_cases.json"))
    yield
