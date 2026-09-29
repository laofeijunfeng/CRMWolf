"""Idempotent assistant requests and lease-fenced turn/event ledger."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class AssistantRequest(Base):
    __tablename__ = "crm_assistant_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crm_assistant_tasks.id"), nullable=False)
    turn_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now)

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", "client_request_id", name="uq_assistant_request_owner_key"),
    )


class AssistantTurn(Base):
    __tablename__ = "crm_assistant_turns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, default=lambda: generate_public_id("atn"))
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crm_assistant_tasks.id"), nullable=False)
    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crm_assistant_requests.id"), nullable=False, unique=True)
    input_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now)
    last_modified_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now)

    __table_args__ = (
        Index("idx_assistant_turn_recover", "status", "lease_expires_at", "id"),
        Index("idx_assistant_turn_task", "team_id", "task_id", "id"),
    )


class AssistantTurnEvent(Base):
    __tablename__ = "crm_assistant_turn_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crm_assistant_turns.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    data_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now)

    __table_args__ = (
        UniqueConstraint("turn_id", "seq", name="uq_assistant_turn_event_sequence"),
    )
