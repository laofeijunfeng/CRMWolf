"""Checkpoint-safe routing contracts for privileged recovery schedulers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CustomerActivityPostCommitRecoveryCandidate(BaseModel):
    """Minimal routing identity emitted by the system post-commit scan."""

    model_config = ConfigDict(frozen=True)

    team_id: int
    job_public_id: str


class FollowUpConfirmationDeliveryRecoveryCandidate(BaseModel):
    """Durable delivery contract emitted by the system confirmation scan."""

    model_config = ConfigDict(frozen=True)

    delivery_public_id: str
    case_public_id: str
    team_id: int
    owner_id: str
    channel: str
    purpose: str
    provider: str | None = None
    recipient_id: str | None = None
    agent_session_id: int | None = None
    origin_turn_id: str | None = None
    origin_message_id: str | None = None
    source_activity_id: int | None = None
    expected_activity_revision: int | None = None
