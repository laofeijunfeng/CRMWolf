"""Checkpoint-safe contracts for follow-up confirmation delivery."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.models.sales_commitment import FollowUpTaskConfirmationDeliveryPurpose


class ConfirmationDeliveryInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_public_id: str
    team_id: int
    owner_id: str
    channel: str
    purpose: str = FollowUpTaskConfirmationDeliveryPurpose.INBOX_VISIBILITY
    provider: str | None = None
    recipient_id: str | None = None
    agent_session_id: int | None = None
    origin_turn_id: str | None = None
    origin_message_id: str | int | None = None
    source_activity_id: int | None = None
    expected_activity_revision: int | None = None
    delivery_public_id: str | None = None
    idempotency_key: str | None = None


class ConfirmationDispatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["SENT", "FAILED", "SKIPPED"]
    provider_message_id: str | None = None
    reason_code: str | None = None
    error_message: str | None = None

    @classmethod
    def sent(cls, *, provider_message_id: str) -> ConfirmationDispatchResult:
        return cls(status="SENT", provider_message_id=provider_message_id, reason_code="CHANNEL_ACKNOWLEDGED")

    @classmethod
    def failed(cls, reason_code: str, error_message: str) -> ConfirmationDispatchResult:
        return cls(status="FAILED", reason_code=reason_code, error_message=error_message)

    @classmethod
    def skipped(cls, reason_code: str, error_message: str | None = None) -> ConfirmationDispatchResult:
        return cls(status="SKIPPED", reason_code=reason_code, error_message=error_message)


class ConfirmationDeliveryAdapter(Protocol):
    async def dispatch(
        self,
        request: ConfirmationDeliveryInput,
        *,
        prompt: dict[str, object],
    ) -> ConfirmationDispatchResult: ...
