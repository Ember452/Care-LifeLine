from care_lifeline.graph.state import AgentState, last_user_text
from care_lifeline.llm.prompts import TRIAGE_PROMPT, render


def triage_node(state: AgentState, provider) -> dict:
    """分诊节点：用分诊 rubric 约束模型，轻量模型即可胜任（tier="fast"）。

    system 消息只承载提示词，用户输入单独作为 user 消息，
    这样 mock provider 仍能按原始输入做确定性匹配。
    """
    text = last_user_text(state["messages"])
    system_prompt = render(TRIAGE_PROMPT, memory_context=state.get("memory_context") or "无")
    draft = provider.complete(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
        tier="fast",
    )
    return {"draft": draft}
