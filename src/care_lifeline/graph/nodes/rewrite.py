"""Agent 循环中的「重写」节点：按质控提醒项补全草稿。

采用确定性修复而非再次调用 LLM：mock 模式下零网络依赖，且保证每次重写都严格
减少提醒项，从而保证循环必然收敛（见 builder._MAX_RETRY）。
"""

from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.safety.keywords import CITATION_MARKERS

DISCLAIMER_LINE = "（免责声明：本回复仅供参考，不替代执业医师的诊断与治疗建议。）"
CITATION_NOTE = "（说明：本条回复未附指南引用，请以线下执业医师意见为准。）"


def rewrite_node(state: AgentState, provider: LLMProvider | None = None) -> dict[str, object]:
    """补全草稿里缺失的免责声明与引用说明，并把 ``retry_count`` 加一。

    Args:
        state: 当前图状态，读取 ``draft`` 与 ``retry_count``。
        provider: 未使用（保留统一节点签名）。

    Returns:
        含修正后 ``draft`` 与自增 ``retry_count`` 的增量更新。
    """
    draft = state.get("draft") or ""
    if "免责" not in draft:
        draft = f"{draft}\n{DISCLAIMER_LINE}"
    if not any(marker in draft for marker in CITATION_MARKERS):
        draft = f"{draft}\n{CITATION_NOTE}"
    return {"draft": draft, "retry_count": state.get("retry_count", 0) + 1}
