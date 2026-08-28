from __future__ import annotations

import os
from pathlib import Path

import coverage


def pytest_sessionfinish(session, exitstatus) -> None:
    """安全红线门禁：src/care_lifeline/safety 覆盖率必须 = 100%（P1-2）。

    在 session 收尾执行（conftest 钩子晚于 pytest-cov 落盘），读取本次
    coverage 数据校验 safety 模块；未启用 ``--cov`` 时跳过，不影响普通测试，
    也避免陈旧 ``.coverage`` 文件误触发。
    """
    cov_source = session.config.getoption("cov_source", None)
    if not cov_source:
        return
    data_file = os.environ.get("COVERAGE_FILE") or ".coverage"
    if not Path(data_file).exists():
        return
    cov = coverage.Coverage(data_file=data_file)
    cov.load()
    total = cov.report(include=["*/care_lifeline/safety/*"], show_missing=True, skip_empty=True)
    if total < 100.0:
        raise RuntimeError(f"安全模块 coverage 门禁失败: {total:.2f}% (<100%)")
