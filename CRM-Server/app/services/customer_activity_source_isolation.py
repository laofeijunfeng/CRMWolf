"""Trace activity-backed intelligence evidence to permitted legacy origins."""

from __future__ import annotations

from sqlalchemy import and_, exists, or_, select

from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.services.customer_activity_contracts import CustomerActivitySubmissionSource


def eligible_activity_source(team_id: int, customer_id: int, activity_id: object):
    """SQL predicate requiring a live activity or deletion tombstone of legacy origin."""
    return or_(
        exists(
            select(1).where(
                CustomerActivity.team_id == team_id,
                CustomerActivity.customer_id == customer_id,
                CustomerActivity.id == activity_id,
                CustomerActivity.submission_source != CustomerActivitySubmissionSource.ASSISTANT_2.value,
            )
        ),
        exists(
            select(1).where(
                CustomerActivityDeletionTombstone.team_id == team_id,
                CustomerActivityDeletionTombstone.customer_id == customer_id,
                CustomerActivityDeletionTombstone.activity_id == activity_id,
                CustomerActivityDeletionTombstone.submission_source != CustomerActivitySubmissionSource.ASSISTANT_2.value,
            )
        ),
    )
