from __future__ import annotations

from care_lifeline.config import get_settings

_CHECKPOINTER = None


def get_checkpointer():
    """Return a LangGraph PostgresSaver when running on PostgreSQL, else ``None``.

    The saver keeps a connection pool and is created once (lazy). On SQLite the
    graph runs without a checkpointer, so conversation recovery is a Postgres-only
    capability, matching the plan (会话恢复 + HITL 时间旅行).
    """
    global _CHECKPOINTER
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        return None
    if _CHECKPOINTER is None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        _CHECKPOINTER = AsyncPostgresSaver.from_conn_string(settings.database_url)
    return _CHECKPOINTER


async def ensure_checkpointer_setup() -> None:
    """Create checkpoint tables once at startup (no-op on SQLite)."""
    saver = get_checkpointer()
    if saver is None:
        return
    async with saver:
        pass
