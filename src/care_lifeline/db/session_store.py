from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select

from care_lifeline.api.security import hash_password, verify_password
from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import AuditLog, Message, QcHit, Session, User


def _to_langchain_message(row: Message):
    if row.role == "user":
        return HumanMessage(row.content)
    return AIMessage(row.content)


def get_or_create_session(
    thread_id: str,
    user_id: int | None = None,
    title: str | None = None,
) -> Session:
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(Session).where(Session.thread_id == thread_id)
        existing = session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing
        row = Session(thread_id=thread_id, user_id=user_id, title=title)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def append_message(
    session_id: int,
    role: str,
    content: str,
    citations: list[dict] | None = None,
) -> Message:
    maker = get_sessionmaker()
    with maker() as session:
        row = Message(
            session_id=session_id,
            role=role,
            content=content,
            citations=citations or [],
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def record_qc_hits(session_id: int, message_id: int, hits: list[QcHit]) -> None:
    if not hits:
        return
    maker = get_sessionmaker()
    with maker() as session:
        for hit in hits:
            hit.session_id = session_id
            hit.message_id = message_id
            session.add(hit)
        session.commit()


def write_audit(session_id: int | None, event: str, detail: str | None = None) -> None:
    maker = get_sessionmaker()
    with maker() as session:
        session.add(AuditLog(session_id=session_id, event=event, detail=detail))
        session.commit()


def list_sessions(user_id: int | None = None) -> list[Session]:
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(Session).order_by(Session.updated_at.desc())
        if user_id is not None:
            stmt = stmt.where(Session.user_id == user_id)
        return list(session.execute(stmt).scalars().all())


def get_messages(session_id: int) -> list[Message]:
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(Message).where(Message.session_id == session_id).order_by(Message.id)
        return list(session.execute(stmt).scalars().all())


def get_prior_messages(session_id: int) -> list:
    return [_to_langchain_message(r) for r in get_messages(session_id)]


def append_clinician_message(session_id: int, content: str) -> Message:
    return append_message(session_id, "clinician", content)


def get_session_by_thread_id(thread_id: str) -> Session | None:
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(Session).where(Session.thread_id == thread_id)
        return session.execute(stmt).scalar_one_or_none()


def list_hitl_sessions() -> list[Session]:
    maker = get_sessionmaker()
    with maker() as session:
        stmt = (
            select(Session)
            .join(QcHit, QcHit.session_id == Session.id)
            .where(QcHit.severity == "hitl")
            .distinct()
            .order_by(Session.updated_at.desc())
        )
        return list(session.execute(stmt).scalars().all())


def get_user_by_username(username: str) -> User | None:
    maker = get_sessionmaker()
    with maker() as session:
        return session.execute(select(User).where(User.username == username)).scalar_one_or_none()


def create_user(username: str, password: str) -> User:
    maker = get_sessionmaker()
    with maker() as session:
        user = User(username=username, hashed_password=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def verify_user(username: str, password: str) -> User | None:
    user = get_user_by_username(username)
    if user is None or user.hashed_password is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def seed_demo_user(username: str = "demo", password: str = "demo123") -> None:
    maker = get_sessionmaker()
    with maker() as session:
        exists = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if exists is None:
            session.add(User(username=username, hashed_password=hash_password(password)))
            session.commit()
