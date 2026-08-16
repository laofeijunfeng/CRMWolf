"""Transactional revision fencing for customer-activity side effects.

The post-commit revision is a write-generation token.  Any workflow that was
created for an older generation must revalidate it while holding the activity
row lock in the same transaction as each downstream CRM mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.customer_activity import CustomerActivity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class CustomerActivityRevisionFenceReason:
    ACTIVITY_NOT_FOUND = "ACTIVITY_NOT_FOUND"
    SUPERSEDED_ACTIVITY_REVISION = "SUPERSEDED_ACTIVITY_REVISION"


@dataclass(frozen=True)
class CustomerActivityRevisionFenceResult:
    activity: CustomerActivity | None
    expected_revision: int
    actual_revision: int | None
    reason: str | None

    @property
    def allowed(self) -> bool:
        return self.reason is None and self.activity is not None


class CustomerActivityRevisionFence:
    """Own the tenant-scoped row-lock and revision comparison contract."""

    def lock_for_mutation(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        expected_revision: int,
    ) -> CustomerActivityRevisionFenceResult:
        activity = (
            db.query(CustomerActivity)
            .filter(
                CustomerActivity.id == activity_id,
                CustomerActivity.team_id == team_id,
            )
            .populate_existing()
            .with_for_update()
            .one_or_none()
        )
        if activity is None:
            return CustomerActivityRevisionFenceResult(
                activity=None,
                expected_revision=expected_revision,
                actual_revision=None,
                reason=CustomerActivityRevisionFenceReason.ACTIVITY_NOT_FOUND,
            )

        actual_revision = int(activity.post_commit_revision or 1)
        if actual_revision != expected_revision:
            return CustomerActivityRevisionFenceResult(
                activity=activity,
                expected_revision=expected_revision,
                actual_revision=actual_revision,
                reason=CustomerActivityRevisionFenceReason.SUPERSEDED_ACTIVITY_REVISION,
            )
        return CustomerActivityRevisionFenceResult(
            activity=activity,
            expected_revision=expected_revision,
            actual_revision=actual_revision,
            reason=None,
        )


customer_activity_revision_fence = CustomerActivityRevisionFence()
