"""用药智能体节点：ReAct 工具循环 + 确定性 DDI 警示双通道。"""

from __future__ import annotations

from care_lifeline.graph.nodes.tool_agent import ToolAgentConfig, run_tool_agent
from care_lifeline.graph.state import AgentState, last_user_text
from care_lifeline.llm.prompts import MEDICATION_PROMPT, render
from care_lifeline.llm.provider import LLMProvider
from care_lifeline.tools.medication import MedicationAgent

# 用药智能体可用工具：相互作用查询 + 指南检索（由模型自主决定是否调用）。
_MEDICATION_TOOLS = ("drug_interaction", "guideline_search")


async def medication_node(state: AgentState, provider: LLMProvider) -> dict[str, object]:
    """用药智能体节点。

    LLM 经原生 tool-calling 自主决定查询相互作用/指南并基于结果作答
    （真实工具轨迹记入 ``tool_traces``）；同时保留离线 DDI 确定性警示
    兜底模型漏检，两路在 responder 合并进最终回复。
    """
    agent = MedicationAgent()
    drugs = agent.extract_drugs(last_user_text(state["messages"]))
    warnings = agent.warnings(drugs)
    outcome = await run_tool_agent(
        state,
        provider,
        ToolAgentConfig(
            system_prompt=render(
                MEDICATION_PROMPT, memory_context=state.get("memory_context") or "无"
            ),
            tool_names=_MEDICATION_TOOLS,
        ),
    )
    return {
        "medication_warnings": warnings,
        "draft": outcome.draft,
        "tool_traces": outcome.traces,
    }
