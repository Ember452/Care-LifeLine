from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import delete, select

from care_lifeline.api.security import hash_password, verify_password
from care_lifeline.db.engine import get_sessionmaker
from care_lifeline.db.models import AuditLog, HitlReview, Message, QcHit, Session, User


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


def create_user(
    username: str, password: str, role: str = "patient", display_name: str | None = None
) -> User:
    """创建用户；用户名重复时抛 IntegrityError（由调用方转成 409）。"""
    maker = get_sessionmaker()
    with maker() as session:
        user = User(
            username=username,
            hashed_password=hash_password(password),
            role=role,
            display_name=display_name,
        )
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


# 种子用户（契约 §8）：admin / doctor / demo 三种角色。
_DEMO_USERS: tuple[tuple[str, str, str], ...] = (
    ("admin", "admin123", "admin"),
    ("doctor", "doctor123", "clinician"),
    ("demo", "demo123", "patient"),
)


def seed_demo_user() -> None:
    """幂等写入三个演示账号（admin/doctor/demo）。"""
    maker = get_sessionmaker()
    with maker() as session:
        for username, password, role in _DEMO_USERS:
            exists = session.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    User(
                        username=username,
                        hashed_password=hash_password(password),
                        role=role,
                    )
                )
        session.commit()


def delete_session(thread_id: str) -> bool:
    """按 thread_id 删除会话（连同消息与审计）。

    Returns:
        是否真的删除了某行。
    """
    maker = get_sessionmaker()
    with maker() as session:
        target = session.execute(
            select(Session).where(Session.thread_id == thread_id)
        ).scalar_one_or_none()
        if target is None:
            return False
        session.execute(delete(Message).where(Message.session_id == target.id))
        session.execute(delete(AuditLog).where(AuditLog.session_id == target.id))
        session.execute(delete(QcHit).where(QcHit.session_id == target.id))
        session.delete(target)
        session.commit()
        return True


def list_audit_logs(
    event: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    """分页查询审计流（admin 后台）。

    Args:
        event: 事件类型过滤（如 ``phi_leak`` / ``chat_completed``）。
        limit: 每页条数。
        offset: 偏移量。

    Returns:
        按时间倒序的审计记录列表。
    """
    maker = get_sessionmaker()
    with maker() as session:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        if event:
            stmt = stmt.where(AuditLog.event == event)
        stmt = stmt.limit(limit).offset(offset)
        return list(session.execute(stmt).scalars().all())


def create_hitl_review(
    session_id: int,
    thread_id: str,
    input_text: str,
    draft: str,
    qc_json: str = "{}",
    violations_json: str = "[]",
    patient_context: str | None = None,
) -> HitlReview:
    maker = get_sessionmaker()
    with maker() as session:
        review = HitlReview(
            session_id=session_id,
            thread_id=thread_id,
            input_text=input_text,
            draft=draft,
            qc_json=qc_json,
            violations_json=violations_json,
            patient_context=patient_context,
            status="pending",
        )
        session.add(review)
        session.commit()
        session.refresh(review)
        return review


def list_pending_reviews() -> list[HitlReview]:
    maker = get_sessionmaker()
    with maker() as session:
        stmt = (
            select(HitlReview)
            .where(HitlReview.status == "pending")
            .order_by(HitlReview.created_at.desc())
        )
        return list(session.execute(stmt).scalars().all())


def get_review(review_id: int) -> HitlReview | None:
    maker = get_sessionmaker()
    with maker() as session:
        return session.execute(
            select(HitlReview).where(HitlReview.id == review_id)
        ).scalar_one_or_none()


def resolve_review(
    review_id: int, decision: str, reviewer: str, corrected_text: str | None = None
) -> HitlReview | None:
    maker = get_sessionmaker()
    with maker() as session:
        review = session.execute(
            select(HitlReview).where(HitlReview.id == review_id)
        ).scalar_one_or_none()
        if review is None:
            return None
        review.status = decision
        review.decision = decision
        review.reviewer = reviewer
        review.corrected_text = corrected_text
        from datetime import datetime

        review.reviewed_at = datetime.now()
        session.commit()
        session.refresh(review)
        return review
