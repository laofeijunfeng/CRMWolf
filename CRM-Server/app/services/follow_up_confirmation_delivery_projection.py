"""Application projection for durable follow-up confirmation delivery.

This module owns every database transaction in the delivery lifecycle.  The
LangGraph workflow only persists JSON-safe lifecycle state and asks this
projection to perform one durable operation at a time.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.crud.customer import customer_crud
from app.crud.sales_commitment import (
    FollowUpTaskConfirmationPromptDeliveryCRUD,
    follow_up_task_confirmation_prompt_delivery_crud,
    follow_up_task_crud,
)
from app.models.sales_commitment import (
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationStatus,
)
from app.services.follow_up_confirmation_case_revision_guard import (
    FollowUpConfirmationCaseRevisionGuard,
    FollowUpConfirmationSourceRevisionContract,
    follow_up_confirmation_case_revision_guard,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.sales_commitment import (
        FollowUpTaskConfirmationCase,
        FollowUpTaskConfirmationPromptDelivery,
    )
    from app.services.follow_up_confirmation_delivery_contracts import ConfirmationDeliveryInput


class ConfirmationProjectionResult(BaseModel):
    """JSON-safe result returned across the graph/application boundary."""

    model_config = ConfigDict(frozen=True)

    phase: Literal["ENSURED", "CLAIMED", "TERMINAL", "ACKNOWLEDGED"]
    status: str
    execution_status: str
    delivery_public_id: str | None = None
    prompt: dict[str, Any] | None = None
    lease_token: str | None = None
    reason_code: str | None = None
    error_message: str | None = None
    provider_message_id: str | None = None

    def as_state_update(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class FollowUpConfirmationDeliveryProjection:
    """Transactional projection for queue, lease and acknowledgement.

    Callers never receive ORM objects.  All tenant/owner/case bindings are
    revalidated at each durable boundary so replay and concurrent mutation fail
    closed instead of dispatching a prompt to the wrong user.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        delivery_crud: FollowUpTaskConfirmationPromptDeliveryCRUD = follow_up_task_confirmation_prompt_delivery_crud,
        case_revision_guard: FollowUpConfirmationCaseRevisionGuard = (
            follow_up_confirmation_case_revision_guard
        ),
    ) -> None:
        self._session_factory = session_factory
        self._delivery_crud = delivery_crud
        self._case_revision_guard = case_revision_guard

    def ensure_and_validate(
        self,
        request: ConfirmationDeliveryInput,
        *,
        prompt_key: str,
        thread_id: str,
    ) -> ConfirmationProjectionResult:
        db = self._session_factory()
        try:
            guard = self._case_revision_guard.lock_and_validate(
                db,
                team_id=request.team_id,
                case_public_id=request.case_public_id,
                requested_contract=self._requested_contract(request),
            )
            case = guard.case
            if case is None:
                return self._terminal_without_delivery(guard.reason or "CASE_NOT_FOUND")

            task = follow_up_task_crud.get_by_id(db, case.task_id, team_id=request.team_id)
            customer = customer_crud.get_by_id(db, case.customer_id, team_id=request.team_id)
            prompt = {
                "case_public_id": case.public_id,
                "question_text": case.question_text,
                "suggested_action": case.suggested_action,
                "task_public_id": task.public_id if task is not None else None,
                "task_title": task.title if task is not None else None,
                "customer_public_id": customer.public_id if customer is not None else None,
                "customer_name": customer.account_name if customer is not None else None,
                "choices": ["已完成", "先放着", "不管了"],
            }

            if request.delivery_public_id:
                delivery = self._delivery_crud.get_by_public_id(
                    db,
                    team_id=request.team_id,
                    public_id=request.delivery_public_id,
                )
                if delivery is None:
                    db.commit()
                    return self._terminal_without_delivery("DELIVERY_NOT_FOUND")
                binding_reason = self._delivery_binding_mismatch_reason(
                    request,
                    delivery=delivery,
                    case_id=case.id,
                    contract=guard.contract,
                )
                if binding_reason:
                    return self._terminalize_binding_mismatch(
                        db,
                        delivery=delivery,
                        reason_code=binding_reason,
                    )
            else:
                delivery = self._delivery_crud.ensure_queued(
                    db,
                    team_id=request.team_id,
                    case_id=case.id,
                    owner_id=request.owner_id,
                    channel=request.channel,
                    purpose=request.purpose,
                    provider=request.provider,
                    recipient_id=request.recipient_id,
                    agent_session_id=request.agent_session_id,
                    interaction_id=f"delivery:{case.public_id}",
                    prompt_key=prompt_key,
                    origin_turn_id=request.origin_turn_id,
                    origin_message_id=str(request.origin_message_id) if request.origin_message_id is not None else None,
                    source_activity_id=guard.contract.source_activity_id,
                    expected_activity_revision=guard.contract.activity_revision,
                    payload_json=prompt,
                    thread_id=thread_id,
                    run_id=uuid4().hex,
                    commit=False,
                )

            skip_reason = self._validation_skip_reason(
                request,
                case=case,
                task_exists=task is not None,
                customer_exists=customer is not None,
                revision_reason=guard.reason,
            )
            if skip_reason and delivery.status != FollowUpTaskConfirmationPromptStatus.SENT:
                self._delivery_crud.acknowledge_skipped(
                    db,
                    delivery,
                    reason_code=skip_reason,
                    commit=False,
                )

            db.commit()
            db.refresh(delivery)
            if delivery.status in FollowUpTaskConfirmationPromptStatus.TERMINAL:
                return self._terminal_from_delivery(delivery, prompt=prompt)
            return ConfirmationProjectionResult(
                phase="ENSURED",
                status=delivery.status,
                execution_status="QUEUED",
                delivery_public_id=delivery.public_id,
                prompt=prompt,
                reason_code=delivery.reason_code,
                provider_message_id=delivery.provider_message_id,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def claim(
        self,
        request: ConfirmationDeliveryInput,
        *,
        delivery_public_id: str,
    ) -> ConfirmationProjectionResult:
        settings = get_settings()
        now = business_now()
        db = self._session_factory()
        try:
            guard = self._case_revision_guard.lock_and_validate(
                db,
                team_id=request.team_id,
                case_public_id=request.case_public_id,
                requested_contract=self._requested_contract(request),
            )
            case = guard.case
            if case is None:
                return self._terminal_without_delivery(guard.reason or "CASE_NOT_FOUND")

            delivery = self._delivery_crud.get_by_public_id_for_update(
                db,
                team_id=request.team_id,
                public_id=delivery_public_id,
            )
            if delivery is None:
                db.commit()
                return self._terminal_without_delivery("DELIVERY_NOT_FOUND")

            binding_reason = self._delivery_binding_mismatch_reason(
                request,
                delivery=delivery,
                case_id=case.id,
                contract=guard.contract,
            )
            if binding_reason:
                return self._terminalize_binding_mismatch(
                    db,
                    delivery=delivery,
                    reason_code=binding_reason,
                )

            skip_reason = self._validation_skip_reason(
                request,
                case=case,
                task_exists=follow_up_task_crud.get_by_id(db, case.task_id, team_id=request.team_id) is not None,
                customer_exists=customer_crud.get_by_id(db, case.customer_id, team_id=request.team_id) is not None,
                revision_reason=guard.reason,
            )
            if skip_reason and delivery.status != FollowUpTaskConfirmationPromptStatus.SENT:
                delivery = self._delivery_crud.acknowledge_skipped(
                    db,
                    delivery,
                    reason_code=skip_reason,
                    commit=False,
                )
                db.commit()
                db.refresh(delivery)
                return self._terminal_from_delivery(delivery)

            if delivery.status in FollowUpTaskConfirmationPromptStatus.TERMINAL:
                return self._terminal_from_delivery(delivery)

            max_attempts = max(1, settings.FOLLOW_UP_CONFIRMATION_DELIVERY_MAX_ATTEMPTS)
            if int(delivery.attempt_count or 0) >= max_attempts:
                delivery = self._delivery_crud.acknowledge_exhausted(
                    db,
                    delivery,
                    error_message=delivery.error_message or "confirmation delivery retries exhausted",
                    commit=False,
                )
                db.commit()
                db.refresh(delivery)
                return self._retries_exhausted_from_delivery(delivery)

            lease_token = uuid4().hex
            claimed = self._delivery_crud.claim_for_dispatch(
                db,
                team_id=request.team_id,
                public_id=delivery.public_id,
                lease_token=lease_token,
                lease_expires_at=now
                + timedelta(seconds=max(1, settings.FOLLOW_UP_CONFIRMATION_DELIVERY_LEASE_SECONDS)),
                max_attempts=max_attempts,
                now=now,
                commit=False,
            )
            if claimed is None:
                db.rollback()
                current = self._delivery_crud.get_by_public_id(
                    db,
                    team_id=request.team_id,
                    public_id=delivery_public_id,
                )
                return self._unclaimed_result(current, now=now)

            db.commit()
            db.refresh(claimed)
            return ConfirmationProjectionResult(
                phase="CLAIMED",
                status=claimed.status,
                execution_status="CLAIMED",
                delivery_public_id=claimed.public_id,
                prompt=dict(claimed.payload_json or {}),
                lease_token=lease_token,
                reason_code=claimed.reason_code,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def acknowledge(
        self,
        request: ConfirmationDeliveryInput,
        *,
        delivery_public_id: str,
        lease_token: str,
        dispatch_status: str,
        provider_message_id: str | None,
        reason_code: str | None,
        error_message: str | None,
    ) -> ConfirmationProjectionResult:
        """Persist the transport result behind a final visibility fence.

        A dispatch lease cannot be held across network I/O.  The source activity
        or confirmation case can therefore change after claim and before the
        provider acknowledges delivery.  We re-lock case -> activity -> delivery
        here and distinguish a stale-but-visible prompt from a prompt suppressed
        before visibility instead of silently reporting a normal SENT result.
        """

        settings = get_settings()
        max_attempts = max(1, settings.FOLLOW_UP_CONFIRMATION_DELIVERY_MAX_ATTEMPTS)
        db = self._session_factory()
        try:
            guard = self._case_revision_guard.lock_and_validate(
                db,
                team_id=request.team_id,
                case_public_id=request.case_public_id,
                requested_contract=self._requested_contract(request),
            )
            case = guard.case
            delivery = self._delivery_crud.get_by_public_id_for_update(
                db,
                team_id=request.team_id,
                public_id=delivery_public_id,
            )
            if delivery is None:
                db.commit()
                return self._terminal_without_delivery("DELIVERY_NOT_FOUND")

            if delivery.status in FollowUpTaskConfirmationPromptStatus.TERMINAL:
                db.commit()
                db.refresh(delivery)
                return self._terminal_from_delivery(delivery)

            if delivery.lease_token != lease_token:
                # Guard-driven source cancellation is independently valid, but
                # the old worker must never write a delivery result after losing
                # its lease.
                db.commit()
                db.refresh(delivery)
                return ConfirmationProjectionResult(
                    phase="TERMINAL",
                    status=delivery.status,
                    execution_status="LEASE_LOST",
                    delivery_public_id=delivery_public_id,
                    reason_code="DISPATCH_LEASE_LOST",
                    provider_message_id=delivery.provider_message_id,
                    error_message=delivery.error_message,
                )

            visibility_reason = guard.reason
            if case is None:
                visibility_reason = visibility_reason or "CASE_NOT_FOUND"
            else:
                visibility_reason = visibility_reason or self._delivery_binding_mismatch_reason(
                    request,
                    delivery=delivery,
                    case_id=case.id,
                    contract=guard.contract,
                )
                visibility_reason = visibility_reason or self._validation_skip_reason(
                    request,
                    case=case,
                    task_exists=(
                        follow_up_task_crud.get_by_id(db, case.task_id, team_id=request.team_id) is not None
                    ),
                    customer_exists=(
                        customer_crud.get_by_id(db, case.customer_id, team_id=request.team_id) is not None
                    ),
                    revision_reason=None,
                )

            attempts_exhausted = int(delivery.attempt_count or 0) >= max_attempts
            stale_after_dispatch = visibility_reason is not None
            if dispatch_status == FollowUpTaskConfirmationPromptStatus.SENT and provider_message_id:
                delivery = self._delivery_crud.acknowledge_sent(
                    db,
                    delivery,
                    provider_message_id=str(provider_message_id),
                    reason_code=(
                        self._stale_dispatch_reason("SENT", visibility_reason)
                        if stale_after_dispatch
                        else reason_code or "CHANNEL_ACKNOWLEDGED"
                    ),
                    commit=False,
                )
            elif dispatch_status == FollowUpTaskConfirmationPromptStatus.SENT:
                delivery = self._delivery_crud.acknowledge_ambiguous(
                    db,
                    delivery,
                    reason_code=(
                        self._stale_dispatch_reason("PROVIDER_ACK_MISSING", visibility_reason)
                        if stale_after_dispatch
                        else "PROVIDER_ACK_MISSING"
                    ),
                    error_message="adapter returned SENT without provider_message_id",
                    commit=False,
                )
            elif dispatch_status == FollowUpTaskConfirmationPromptStatus.FAILED and stale_after_dispatch:
                delivery = self._delivery_crud.acknowledge_skipped(
                    db,
                    delivery,
                    reason_code=self._stale_dispatch_reason("SKIPPED", visibility_reason),
                    error_message=error_message,
                    commit=False,
                )
            elif dispatch_status == FollowUpTaskConfirmationPromptStatus.FAILED and attempts_exhausted:
                delivery = self._delivery_crud.acknowledge_exhausted(
                    db,
                    delivery,
                    error_message=error_message,
                    commit=False,
                )
            elif dispatch_status == FollowUpTaskConfirmationPromptStatus.FAILED:
                delivery = self._delivery_crud.acknowledge_failed(
                    db,
                    delivery,
                    reason_code=reason_code or "CHANNEL_FAILED",
                    error_message=error_message,
                    next_attempt_at=self._next_attempt_at(delivery.attempt_count),
                    commit=False,
                )
            else:
                delivery = self._delivery_crud.acknowledge_skipped(
                    db,
                    delivery,
                    reason_code=(
                        self._stale_dispatch_reason("SKIPPED", visibility_reason)
                        if stale_after_dispatch
                        else reason_code or "DELIVERY_SKIPPED"
                    ),
                    error_message=error_message,
                    commit=False,
                )

            db.commit()
            db.refresh(delivery)
            if delivery.status == FollowUpTaskConfirmationPromptStatus.EXHAUSTED:
                return self._retries_exhausted_from_delivery(delivery)
            return ConfirmationProjectionResult(
                phase=(
                    "TERMINAL"
                    if delivery.status == FollowUpTaskConfirmationPromptStatus.AMBIGUOUS
                    else "ACKNOWLEDGED"
                ),
                status=delivery.status,
                execution_status=(
                    "AMBIGUOUS"
                    if delivery.status == FollowUpTaskConfirmationPromptStatus.AMBIGUOUS
                    else "ACKNOWLEDGED_STALE_AFTER_DISPATCH"
                    if stale_after_dispatch
                    else "ACKNOWLEDGED"
                ),
                delivery_public_id=delivery.public_id,
                reason_code=delivery.reason_code,
                error_message=delivery.error_message,
                provider_message_id=delivery.provider_message_id,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _terminalize_binding_mismatch(
        self,
        db: Session,
        *,
        delivery: FollowUpTaskConfirmationPromptDelivery,
        reason_code: str,
    ) -> ConfirmationProjectionResult:
        if delivery.status not in FollowUpTaskConfirmationPromptStatus.TERMINAL:
            delivery = self._delivery_crud.acknowledge_skipped(
                db,
                delivery,
                reason_code=reason_code,
                commit=False,
            )
        db.commit()
        db.refresh(delivery)
        result = self._terminal_from_delivery(delivery)
        if result.reason_code == reason_code:
            return result
        return result.model_copy(update={"reason_code": reason_code})

    @staticmethod
    def _stale_dispatch_reason(outcome: str, visibility_reason: str | None) -> str:
        normalized_reason = str(visibility_reason or "VISIBILITY_INVALIDATED").strip().upper()
        return f"{outcome}_STALE_{normalized_reason}"[:80]

    @staticmethod
    def _delivery_binding_mismatch_reason(
        request: ConfirmationDeliveryInput,
        *,
        delivery: FollowUpTaskConfirmationPromptDelivery,
        case_id: int,
        contract: FollowUpConfirmationSourceRevisionContract,
    ) -> str | None:
        if delivery.case_id != case_id:
            return "DELIVERY_CASE_MISMATCH"
        if str(delivery.owner_id) != str(request.owner_id):
            return "DELIVERY_OWNER_MISMATCH"
        if delivery.channel != request.channel or delivery.purpose != request.purpose:
            return "DELIVERY_CHANNEL_MISMATCH"
        if (delivery.provider or None) != (request.provider or None):
            return "DELIVERY_PROVIDER_MISMATCH"
        if delivery.agent_session_id != request.agent_session_id:
            return "DELIVERY_SESSION_MISMATCH"
        if delivery.source_activity_id != contract.source_activity_id:
            return "DELIVERY_SOURCE_ACTIVITY_MISMATCH"
        if delivery.expected_activity_revision != contract.activity_revision:
            return "DELIVERY_ACTIVITY_REVISION_MISMATCH"
        return None

    @staticmethod
    def _validation_skip_reason(
        request: ConfirmationDeliveryInput,
        *,
        case: FollowUpTaskConfirmationCase,
        task_exists: bool,
        customer_exists: bool,
        revision_reason: str | None,
    ) -> str | None:
        if revision_reason is not None:
            return revision_reason
        if str(case.owner_id) != str(request.owner_id):
            return "OWNER_MISMATCH"
        if case.status != FollowUpTaskConfirmationStatus.PENDING:
            return "CASE_NOT_PENDING"
        if case.expires_at is not None and case.expires_at <= business_now():
            return "CASE_EXPIRED"
        if not task_exists:
            return "TASK_NOT_FOUND"
        if not customer_exists:
            return "CUSTOMER_NOT_FOUND"
        return None

    @staticmethod
    def _requested_contract(
        request: ConfirmationDeliveryInput,
    ) -> FollowUpConfirmationSourceRevisionContract | None:
        if request.source_activity_id is None and request.expected_activity_revision is None:
            return None
        return FollowUpConfirmationSourceRevisionContract(
            source_activity_id=request.source_activity_id,
            activity_revision=request.expected_activity_revision,
        )

    @staticmethod
    def _terminal_without_delivery(
        reason_code: str,
        *,
        delivery_public_id: str | None = None,
        status: str = FollowUpTaskConfirmationPromptStatus.SKIPPED,
    ) -> ConfirmationProjectionResult:
        return ConfirmationProjectionResult(
            phase="TERMINAL",
            status=status,
            execution_status="TERMINAL",
            delivery_public_id=delivery_public_id,
            reason_code=reason_code,
        )

    @staticmethod
    def _terminal_from_delivery(
        delivery: FollowUpTaskConfirmationPromptDelivery,
        *,
        prompt: dict[str, Any] | None = None,
    ) -> ConfirmationProjectionResult:
        return ConfirmationProjectionResult(
            phase="TERMINAL",
            status=delivery.status,
            execution_status="TERMINAL",
            delivery_public_id=delivery.public_id,
            prompt=prompt or dict(delivery.payload_json or {}),
            reason_code=delivery.reason_code,
            error_message=delivery.error_message,
            provider_message_id=delivery.provider_message_id,
        )

    @staticmethod
    def _retries_exhausted_from_delivery(
        delivery: FollowUpTaskConfirmationPromptDelivery,
    ) -> ConfirmationProjectionResult:
        return ConfirmationProjectionResult(
            phase="TERMINAL",
            status=delivery.status,
            execution_status="RETRIES_EXHAUSTED",
            delivery_public_id=delivery.public_id,
            prompt=dict(delivery.payload_json or {}),
            reason_code="DELIVERY_RETRIES_EXHAUSTED",
            error_message=delivery.error_message,
            provider_message_id=delivery.provider_message_id,
        )

    @staticmethod
    def _unclaimed_result(
        delivery: FollowUpTaskConfirmationPromptDelivery | None,
        *,
        now: datetime,
    ) -> ConfirmationProjectionResult:
        if delivery is None:
            return FollowUpConfirmationDeliveryProjection._terminal_without_delivery("DELIVERY_NOT_FOUND")
        if delivery.status in FollowUpTaskConfirmationPromptStatus.TERMINAL:
            return FollowUpConfirmationDeliveryProjection._terminal_from_delivery(delivery)
        if delivery.lease_token and delivery.lease_expires_at and delivery.lease_expires_at > now:
            execution_status = "BUSY"
            reason_code = "DELIVERY_LEASE_BUSY"
        elif delivery.status == FollowUpTaskConfirmationPromptStatus.FAILED and delivery.next_attempt_at:
            execution_status = "DEFERRED"
            reason_code = "DELIVERY_RETRY_NOT_DUE"
        else:
            execution_status = "NOT_CLAIMED"
            reason_code = "DELIVERY_NOT_CLAIMED"
        return ConfirmationProjectionResult(
            phase="TERMINAL",
            status=delivery.status,
            execution_status=execution_status,
            delivery_public_id=delivery.public_id,
            prompt=dict(delivery.payload_json or {}),
            reason_code=reason_code,
            error_message=delivery.error_message,
            provider_message_id=delivery.provider_message_id,
        )

    @staticmethod
    def _next_attempt_at(attempt_count: int | None) -> datetime:
        settings = get_settings()
        base = max(1, settings.FOLLOW_UP_CONFIRMATION_DELIVERY_RETRY_BASE_SECONDS)
        exponent = max(0, int(attempt_count or 1) - 1)
        return business_now() + timedelta(seconds=base * (2**exponent))
