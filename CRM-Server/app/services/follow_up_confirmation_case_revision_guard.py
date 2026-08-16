"""Durable source-activity revision guard for confirmation prompt visibility.

A confirmation case created by an activity post-commit generation may only be
shown while that exact activity revision is still current.  This module owns
the tenant-scoped case lock, source contract validation, activity row lock and
case invalidation so every channel uses the same fail-closed rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.crud.sales_commitment import follow_up_task_confirmation_case_crud
from app.models.sales_commitment import FollowUpTaskConfirmationStatus
from app.services.customer_activity_revision_fence import (
    CustomerActivityRevisionFence,
    customer_activity_revision_fence,
)
from app.services.follow_up_task_confirmation_cleanup_service import (
    FollowUpTaskConfirmationCancelReason,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTaskConfirmationCase


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
    ) -> None:
        self._revision_fence = revision_fence

    def lock_and_validate(
        self,
        db: Session,
        *,
        team_id: int,
        case_public_id: str,
        requested_contract: FollowUpConfirmationSourceRevisionContract | None = None,
    ) -> FollowUpConfirmationCaseRevisionGuardResult:
        case = follow_up_task_confirmation_case_crud.get_by_public_id_for_update(
            db,
            public_id=case_public_id,
            team_id=team_id,
        )
        return self._validate_locked_case(
            db,
            team_id=team_id,
            case=case,
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

        case = follow_up_task_confirmation_case_crud.get_by_id_for_update(
            db,
            case_id=case_id,
            team_id=team_id,
        )
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

    @staticmethod
    def _cancel_invalidated_case(
        db: Session,
        *,
        case: FollowUpTaskConfirmationCase,
        cancelled_reason: str,
    ) -> None:
        if case.status != FollowUpTaskConfirmationStatus.PENDING:
            return
        follow_up_task_confirmation_case_crud.mark_cancelled(
            db,
            case,
            cancelled_reason=cancelled_reason,
            commit=False,
        )


follow_up_confirmation_case_revision_guard = FollowUpConfirmationCaseRevisionGuard()
