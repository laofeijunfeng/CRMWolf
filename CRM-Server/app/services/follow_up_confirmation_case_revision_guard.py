"""Durable source-activity revision guard for confirmation prompt visibility.

A confirmation case created by an activity post-commit generation may only be
shown while that exact activity revision is still current.  This module owns
the tenant-scoped case lock, source contract validation, activity row lock and
case invalidation so every channel uses the same fail-closed rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.sales_commitment import FollowUpTaskConfirmationCase, FollowUpTaskConfirmationStatus
from app.services.customer_activity_revision_fence import (
    CustomerActivityRevisionFence,
    customer_activity_revision_fence,
)
from app.services.follow_up_confirmation_case_lifecycle_service import (
    FollowUpConfirmationCaseLifecycleService,
    follow_up_confirmation_case_lifecycle_service,
)
from app.services.follow_up_task_confirmation_cleanup_service import (
    FollowUpTaskConfirmationCancelReason,
)
from app.services.legacy_profile_source import lock_source_customer

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class FollowUpConfirmationCaseRevisionReason:
    CASE_NOT_FOUND = "CASE_NOT_FOUND"
    SOURCE_ACTIVITY_ID_MISSING = "SOURCE_ACTIVITY_ID_MISSING"
    SOURCE_ACTIVITY_REVISION_MISSING = "SOURCE_ACTIVITY_REVISION_MISSING"
    DELIVERY_SOURCE_ACTIVITY_MISMATCH = "DELIVERY_SOURCE_ACTIVITY_MISMATCH"
    DELIVERY_ACTIVITY_REVISION_MISMATCH = "DELIVERY_ACTIVITY_REVISION_MISMATCH"


@dataclass(frozen=True)
class FollowUpConfirmationSourceRevisionContract:
    source_activity_id: int | None
    activity_revision: int | None


@dataclass(frozen=True)
class FollowUpConfirmationCaseRevisionGuardResult:
    case: FollowUpTaskConfirmationCase | None
    contract: FollowUpConfirmationSourceRevisionContract
    reason: str | None

    @property
    def allowed(self) -> bool:
        return self.case is not None and self.reason is None


class FollowUpConfirmationCaseRevisionGuard:
    """Lock and validate one confirmation case's source generation contract."""

    def __init__(
        self,
        *,
        revision_fence: CustomerActivityRevisionFence = customer_activity_revision_fence,
        case_lifecycle: FollowUpConfirmationCaseLifecycleService = (
            follow_up_confirmation_case_lifecycle_service
        ),
    ) -> None:
        self._revision_fence = revision_fence
        self._case_lifecycle = case_lifecycle

    def lock_and_validate(
        self,
        db: Session,
        *,
        team_id: int,
        case_public_id: str,
        requested_contract: FollowUpConfirmationSourceRevisionContract | None = None,
    ) -> FollowUpConfirmationCaseRevisionGuardResult:
        return self._lock_and_validate(
            db,
            team_id=team_id,
            case_filter=FollowUpTaskConfirmationCase.public_id == case_public_id,
            requested_contract=requested_contract,
        )

    def lock_and_validate_by_id(
        self,
        db: Session,
        *,
        team_id: int,
        case_id: int,
        requested_contract: FollowUpConfirmationSourceRevisionContract | None = None,
    ) -> FollowUpConfirmationCaseRevisionGuardResult:
        """Validate a delivery-bound case without relying on JSON payload fields."""

        return self._lock_and_validate(
            db,
            team_id=team_id,
            case_filter=FollowUpTaskConfirmationCase.id == case_id,
            requested_contract=requested_contract,
        )

    def _lock_and_validate(
        self,
        db: Session,
        *,
        team_id: int,
        case_filter: object,
        requested_contract: FollowUpConfirmationSourceRevisionContract | None,
    ) -> FollowUpConfirmationCaseRevisionGuardResult:
        # Read only the tenant-scoped key before locking anything. A changed
        # customer binding makes the second, locked read miss instead of
        # acquiring a Case lock under the wrong customer's lock.
        with db.no_autoflush:
            source = (
                db.query(FollowUpTaskConfirmationCase.customer_id)
                .filter(FollowUpTaskConfirmationCase.team_id == team_id, case_filter)
                .one_or_none()
            )
            if source is None:
                case = None
            else:
                lock_source_customer(db, team_id=team_id, customer_id=source.customer_id)
                case = (
                    db.query(FollowUpTaskConfirmationCase)
                    .filter(
                        FollowUpTaskConfirmationCase.team_id == team_id,
                        FollowUpTaskConfirmationCase.customer_id == source.customer_id,
                        case_filter,
                    )
                    .with_for_update()
                    .one_or_none()
                )
                if case is not None:
                    if case in db.dirty:
                        db.flush([case])
                    db.refresh(case, with_for_update=True)
        return self._validate_locked_case(
            db,
            team_id=team_id,
            case=case,
            requested_contract=requested_contract,
        )

    def _validate_locked_case(
        self,
        db: Session,
        *,
        team_id: int,
        case: FollowUpTaskConfirmationCase | None,
        requested_contract: FollowUpConfirmationSourceRevisionContract | None,
    ) -> FollowUpConfirmationCaseRevisionGuardResult:
        if case is None:
            return FollowUpConfirmationCaseRevisionGuardResult(
                case=None,
                contract=FollowUpConfirmationSourceRevisionContract(None, None),
                reason=FollowUpConfirmationCaseRevisionReason.CASE_NOT_FOUND,
            )

        contract = FollowUpConfirmationSourceRevisionContract(
            source_activity_id=case.source_activity_id,
            activity_revision=case.source_activity_revision,
        )
        binding_reason = self._binding_reason(contract, requested_contract)
        if binding_reason is not None:
            return FollowUpConfirmationCaseRevisionGuardResult(
                case=case,
                contract=contract,
                reason=binding_reason,
            )

        if contract.source_activity_id is None and contract.activity_revision is None:
            return FollowUpConfirmationCaseRevisionGuardResult(case=case, contract=contract, reason=None)
        if contract.source_activity_id is None:
            self._cancel_invalidated_case(
                db,
                case=case,
                cancelled_reason=FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_REVISION_CONTRACT_INVALID,
            )
            return FollowUpConfirmationCaseRevisionGuardResult(
                case=case,
                contract=contract,
                reason=FollowUpConfirmationCaseRevisionReason.SOURCE_ACTIVITY_ID_MISSING,
            )
        if contract.activity_revision is None:
            self._cancel_invalidated_case(
                db,
                case=case,
                cancelled_reason=FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_REVISION_CONTRACT_INVALID,
            )
            return FollowUpConfirmationCaseRevisionGuardResult(
                case=case,
                contract=contract,
                reason=FollowUpConfirmationCaseRevisionReason.SOURCE_ACTIVITY_REVISION_MISSING,
            )

        fence = self._revision_fence.lock_for_mutation(
            db,
            team_id=team_id,
            activity_id=contract.source_activity_id,
            expected_revision=contract.activity_revision,
            customer_id=case.customer_id,
        )
        if fence.allowed:
            return FollowUpConfirmationCaseRevisionGuardResult(case=case, contract=contract, reason=None)

        cancelled_reason = {
            "SUPERSEDED_ACTIVITY_REVISION": (
                FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_REVISION_SUPERSEDED
            ),
            "ACTIVITY_NOT_FOUND": FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_DELETED,
        }.get(fence.reason)
        if cancelled_reason is not None:
            self._cancel_invalidated_case(db, case=case, cancelled_reason=cancelled_reason)
        return FollowUpConfirmationCaseRevisionGuardResult(
            case=case,
            contract=contract,
            reason=fence.reason,
        )

    @staticmethod
    def _binding_reason(
        persisted: FollowUpConfirmationSourceRevisionContract,
        requested: FollowUpConfirmationSourceRevisionContract | None,
    ) -> str | None:
        if requested is None:
            return None
        if requested.source_activity_id != persisted.source_activity_id:
            return FollowUpConfirmationCaseRevisionReason.DELIVERY_SOURCE_ACTIVITY_MISMATCH
        if requested.activity_revision != persisted.activity_revision:
            return FollowUpConfirmationCaseRevisionReason.DELIVERY_ACTIVITY_REVISION_MISMATCH
        return None

    def _cancel_invalidated_case(
        self,
        db: Session,
        *,
        case: FollowUpTaskConfirmationCase,
        cancelled_reason: str,
    ) -> None:
        if case.status != FollowUpTaskConfirmationStatus.PENDING:
            return
        self._case_lifecycle.cancel_locked_case(
            db,
            team_id=int(case.team_id),
            case=case,
            reason=cancelled_reason,
        )


follow_up_confirmation_case_revision_guard = FollowUpConfirmationCaseRevisionGuard()
