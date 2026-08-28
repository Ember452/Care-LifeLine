from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from care_lifeline.config import Settings, get_settings

_engine: Engine | None = None
_sessionmaker: sessionmaker | None = None


def make_url(settings: Settings) -> str:
    url = settings.database_url
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    if url.startswith("sqlite://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine, _sessionmaker
    if _engine is None:
        resolved = settings or get_settings()
        _engine = create_engine(make_url(resolved), future=True)
        _sessionmaker = sessionmaker(_engine, expire_on_commit=False, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def init_db(engine: Engine | None = None) -> None:
    from care_lifeline.db.models import Base

    eng = engine or get_engine()
    Base.metadata.create_all(eng)


def reset_state_for_testing() -> None:
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
