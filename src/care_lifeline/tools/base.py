from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from care_lifeline.graph.state import Citation


@dataclass
class ToolResult:
    """工具统一返回值（契约 §5）。

    Attributes:
        ok: 执行是否成功。
        data: 结构化结果。
        citations: 工具产生的引用来源。
        error: 失败原因；成功时为 ``None``。
    """

    ok: bool
    data: dict[str, Any]
    citations: list[Citation] = field(default_factory=list)
    error: str | None = None


@runtime_checkable
class CareTool(Protocol):
    """统一工具协议（契约 §5）。

    现有能力（指南检索 / 报告解析 / 用药相互作用 / 指标趋势）以本协议包装，
    供未来 real 模式下的 LLM tool-calling 分支调用；mock 模式走确定性节点。
    """

    name: str
    description: str

    async def run(self, **kwargs: Any) -> ToolResult: ...
