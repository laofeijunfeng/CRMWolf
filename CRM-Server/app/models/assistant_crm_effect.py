"""Immutable receipt identifying an assistant command's committed CRM target effect."""

from datetime import datetime  # noqa: TC003

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.time import business_now


class AssistantCRMEffect(Base):
    __tablename__ = "crm_assistant_crm_effects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    command_id: Mapped[str] = mapped_column(String(64), nullable=False)
    effect_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    target_public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stage_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    previous_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    previous_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resulting_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now)

    __table_args__ = (
        UniqueConstraint("team_id", "command_id", "effect_kind", name="uq_assistant_crm_effect_command"),
    )
