"""Transactional revision fencing for customer-activity side effects.

The post-commit revision is a write-generation token.  Any workflow that was
created for an older generation must revalidate it while holding the activity
row lock in the same transaction as each downstream CRM mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.customer_activity import CustomerActivity
from app.services.legacy_profile_source import lock_source_customer

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
    """Fence an activity under its tenant customer's lock and then its own lock."""

    def lock_for_mutation(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        expected_revision: int,
        customer_id: int | None = None,
    ) -> CustomerActivityRevisionFenceResult:
        # Resolve only the tenant-scoped customer key, without locking or flushing
        # the activity. The customer row must precede the activity row in the
        # lock order shared with legacy-profile publication.
        with db.no_autoflush:
            source = (
                db.query(CustomerActivity.customer_id)
                .filter(CustomerActivity.id == activity_id, CustomerActivity.team_id == team_id)
                .one_or_none()
            )
            if source is None or (customer_id is not None and source.customer_id != customer_id):
                return CustomerActivityRevisionFenceResult(
                    activity=None,
                    expected_revision=expected_revision,
                    actual_revision=None,
                    reason=CustomerActivityRevisionFenceReason.ACTIVITY_NOT_FOUND,
                )

            source_customer_id = source.customer_id
            if source_customer_id is not None:
                lock_source_customer(db, team_id=team_id, customer_id=source_customer_id)
            activity = (
                db.query(CustomerActivity)
                .filter(
                    CustomerActivity.id == activity_id,
                    CustomerActivity.team_id == team_id,
                    CustomerActivity.customer_id == source_customer_id,
                )
                .with_for_update()
                .one_or_none()
            )
        # A caller may already have changed this instance in the transaction.
        # Flush it only after its row is locked, then load the current CAS value.
        if activity is not None:
            if activity in db.dirty:
                db.flush([activity])
            db.refresh(activity, with_for_update=True)
        if activity is None:
            return CustomerActivityRevisionFenceResult(
                activity=None,
                expected_revision=expected_revision,
                actual_revision=None,
                reason=CustomerActivityRevisionFenceReason.ACTIVITY_NOT_FOUND,
            )

        actual_revision = int(activity.activity_revision or 1)
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
