from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable

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

    ``parameters`` 以 JSON Schema 描述参数，供 LLM 原生 tool-calling
    构造工具选择依据；mock 模式下由确定性脚本驱动同一通路。
    """

    name: str
    description: str
    parameters: ClassVar[dict[str, Any]]

    async def run(self, **kwargs: Any) -> ToolResult: ...
