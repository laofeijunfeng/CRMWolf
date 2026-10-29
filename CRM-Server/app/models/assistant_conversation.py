"""Owned continuous conversation and durable routing references (assistant 2.0)."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 -- SQLAlchemy resolves Mapped types at runtime.

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class AssistantConversation(Base):
    __tablename__ = "crm_assistant_conversations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: generate_public_id("asc"))
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    focused_task_public_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_choice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    busy_entry_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=business_now, nullable=False)
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_assistant_conversation_owner"),)


class AssistantConversationEntry(Base):
    __tablename__ = "crm_assistant_conversation_entries"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: generate_public_id("acm"))
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_assistant_conversations.id"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    command_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    decision_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="ROUTING", nullable=False)
    task_public_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    turn_public_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    task_snapshot_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=business_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_request_id", name="uq_assistant_conversation_request"),
        Index("idx_assistant_conversation_page", "team_id", "user_id", "conversation_id", "id"),
    )
