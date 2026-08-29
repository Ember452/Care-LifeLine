"""Trajectory 端点：检查点历史与时间旅行重放（文档 §7.5 / §10.2）。

配合审计轨迹（消息 + 每跳工具 + 质控结论），构成"全链路可追溯"闭环：
``GET .../checkpoints`` 列出某会话在 checkpointer 里的全部状态快照，
``POST .../replay`` 从指定检查点重放其后的执行（时间旅行）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from care_lifeline.api.security import ROLE_ADMIN, CurrentUser, require_roles
from care_lifeline.db import session_store
from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.checkpointer import get_checkpointer
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.provider import make_provider

router = APIRouter(prefix="/v1/admin/trajectories", tags=["admin"])

_require_admin = require_roles(ROLE_ADMIN)


class CheckpointItem(BaseModel):
    """一个检查点的摘要（不返回完整状态值，避免 PHI 大对象出接口）。"""

    checkpoint_id: str
    step: int
    created_at: str | None
    draft: str
    qc_status: str | None
    intent: str | None


class ReplayRequest(BaseModel):
    checkpoint_id: str


class ReplayResponse(BaseModel):
    ok: bool
    final: str
    citations: list[dict]


def _graph_with_checkpointer(thread_id: str):
    """返回 (编译图, config)；无 checkpointer 时抛 409（时间旅行不可用）。"""
    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "checkpointer_unavailable",
                "message": "当前运行模式无会话持久化，不支持轨迹回放",
            },
        )
    graph = build_graph(make_provider(), checkpointer=checkpointer)
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    return graph, config


def _summarize(values: dict[str, Any]) -> tuple[str, str | None, str | None]:
    qc = values.get("qc_result")
    return (
        str(values.get("draft", "") or ""),
        qc.status if qc is not None else None,
        values.get("intent"),
    )


@router.get("/{thread_id}/checkpoints", response_model=list[CheckpointItem])
def list_checkpoints(
    thread_id: str, user: Annotated[CurrentUser, Depends(_require_admin)]
) -> list[CheckpointItem]:
    """按时间倒序列出会话的检查点历史（最新在前）。"""
    graph, config = _graph_with_checkpointer(thread_id)
    items: list[CheckpointItem] = []
    for snapshot in graph.get_state_history(config):
        values: dict[str, Any] = snapshot.values or {}
        draft, qc_status, intent = _summarize(values)
        items.append(
            CheckpointItem(
                checkpoint_id=str(snapshot.config["configurable"]["checkpoint_id"]),
                step=int(snapshot.metadata.get("step", 0)) if snapshot.metadata else 0,
                created_at=str(snapshot.created_at) if snapshot.created_at else None,
                draft=draft,
                qc_status=qc_status,
                intent=intent,
            )
        )
    return items


@router.post("/{thread_id}/replay", response_model=ReplayResponse)
async def replay(
    thread_id: str,
    body: ReplayRequest,
    user: Annotated[CurrentUser, Depends(_require_admin)],
) -> ReplayResponse:
    """时间旅行：从指定检查点重放其后的执行（`ainvoke(None, config=checkpoint)`）。

    重放会在同一线程追加新的检查点（fork），原历史不变；重放动作本身写审计。
    """
    graph, config = _graph_with_checkpointer(thread_id)
    config["configurable"]["checkpoint_id"] = body.checkpoint_id
    try:
        final_state: AgentState = await graph.ainvoke(None, config=config)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "replay_failed", "message": f"重放失败：{type(exc).__name__}"},
        ) from exc

    session = session_store.get_session_by_thread_id(thread_id)
    session_store.write_audit(
        session.id if session is not None else None,
        "trajectory_replayed",
        f"{user.username}:{body.checkpoint_id}",
    )
    return ReplayResponse(
        ok=True,
        final=str(final_state.get("draft", "") or ""),
        citations=[c.model_dump() for c in final_state.get("citations", [])],
    )
