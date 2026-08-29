from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from care_lifeline.config import get_settings

if TYPE_CHECKING:
    from aiosqlite import Connection

_CHECKPOINTER: object | None = None
_SQLITE_CONN: Connection | None = None


def _sqlite_path(database_url: str) -> str:
    """从 ``sqlite(+aiosqlite):///`` URL 提取数据库文件路径。"""
    marker = ":///"
    return database_url.split(marker, 1)[1] if marker in database_url else ":memory:"


def get_checkpointer():
    """返回进程级 LangGraph checkpointer（P1-E）。

    - PostgreSQL：惰性创建 ``AsyncPostgresSaver``（维持既有行为）。
    - SQLite：由 :func:`ensure_checkpointer_setup` 在应用启动时创建并建表，
      使默认开发模式同样具备会话持久化与真 interrupt HITL。
    - 尚未初始化：返回 ``None``，图以无持久化模式运行（评测/裸图调用）。
    """
    global _CHECKPOINTER
    settings = get_settings()
    if settings.database_url.startswith("postgresql"):
        if _CHECKPOINTER is None:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            _CHECKPOINTER = AsyncPostgresSaver.from_conn_string(settings.database_url)
        return _CHECKPOINTER
    return _CHECKPOINTER


async def ensure_checkpointer_setup() -> None:
    """应用启动时初始化 checkpointer 并创建存储表。"""
    global _CHECKPOINTER, _SQLITE_CONN
    settings = get_settings()
    if settings.database_url.startswith("postgresql"):
        saver = get_checkpointer()
        if saver is not None:
            async with saver:
                pass
        return
    if _CHECKPOINTER is None:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        conn = await aiosqlite.connect(_sqlite_path(settings.database_url))
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        _SQLITE_CONN = conn
        _CHECKPOINTER = saver


def reset_checkpointer_for_testing() -> None:
    """测试隔离：丢弃 checkpointer 单例并尽量释放 SQLite 连接线程。"""
    global _CHECKPOINTER, _SQLITE_CONN
    _CHECKPOINTER = None
    if _SQLITE_CONN is not None:
        with contextlib.suppress(Exception):
            _SQLITE_CONN.stop()
        _SQLITE_CONN = None
