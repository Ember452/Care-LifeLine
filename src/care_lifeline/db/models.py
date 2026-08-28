from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="patient")
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CitationRow(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(255))
    snippet: Mapped[str] = mapped_column(Text)


class QcRuleRow(Base):
    __tablename__ = "qc_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1)


class QcHit(Base):
    __tablename__ = "qc_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    rule_code: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
