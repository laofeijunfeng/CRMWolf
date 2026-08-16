"""Transactional application seam for customer-activity writes.

Every activity revision that can affect downstream semantics is committed with
its durable post-commit job and canonical customer-intelligence run. Immediate
execution is deliberately outside this module; recovery owns correctness while
callers may kick the returned requests after commit for low latency.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from app.crud.customer_activity import CustomerActivityCRUD, customer_activity_crud
from app.services.customer_activity_post_commit_job_service import (
    CustomerActivityPostCommitJobRequest,
    CustomerActivityPostCommitJobService,
    customer_activity_post_commit_job_service,
)
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceEventService,
    customer_intelligence_event_service,
)
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceCommittedEventRequest,
    CustomerIntelligenceRefreshService,
    customer_intelligence_refresh_service,
)
from app.services.follow_up_task_confirmation_cleanup_service import (
    FollowUpTaskConfirmationCancelReason,
    FollowUpTaskConfirmationCleanupService,
    follow_up_task_confirmation_cleanup_service,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer_activity import CustomerActivity
    from app.schemas.customer_activity import CustomerActivityCreate, CustomerActivityUpdate


@dataclass(frozen=True)
class CustomerActivityWriteResult:
    activity: CustomerActivity
    activity_revision: int
    post_commit_job: CustomerActivityPostCommitJobRequest | None
    customer_intelligence_request: CustomerIntelligenceCommittedEventRequest | None


class CustomerActivityDurableWorkPolicy(StrEnum):
    ALWAYS = "ALWAYS"
    ON_REVISION_CHANGE = "ON_REVISION_CHANGE"


CustomerActivityBeforeCommit = Callable[[CustomerActivityWriteResult], None]


class CustomerActivityWriteService:
    """Own the atomic activity-write/outbox transaction behind one interface."""

    def __init__(
        self,
        *,
        activity_crud: CustomerActivityCRUD | None = None,
        post_commit_job_service: CustomerActivityPostCommitJobService | None = None,
        intelligence_event_service: CustomerIntelligenceEventService | None = None,
        intelligence_refresh_service: CustomerIntelligenceRefreshService | None = None,
        confirmation_cleanup_service: FollowUpTaskConfirmationCleanupService | None = None,
    ) -> None:
        self.activity_crud = activity_crud or customer_activity_crud
        self.post_commit_job_service = post_commit_job_service or customer_activity_post_commit_job_service
        self.intelligence_event_service = intelligence_event_service or customer_intelligence_event_service
        self.intelligence_refresh_service = intelligence_refresh_service or customer_intelligence_refresh_service
        self.confirmation_cleanup_service = confirmation_cleanup_service or follow_up_task_confirmation_cleanup_service

    def create(
        self,
        db: Session,
        *,
        obj_in: CustomerActivityCreate,
        customer_id: int,
        creator_id: str,
        team_id: int,
        post_commit_trigger_type: str,
        actor_id: str | None,
        operator_name: str | None = None,
        original_lead_id: int | None = None,
        owner_id: str | None = None,
        before_commit: CustomerActivityBeforeCommit | None = None,
    ) -> CustomerActivityWriteResult:
        return self._write(
            db,
            mutate=lambda: self.activity_crud.create(
                db=db,
                obj_in=obj_in,
                customer_id=customer_id,
                creator_id=creator_id,
                team_id=team_id,
                operator_name=operator_name,
                original_lead_id=original_lead_id,
                owner_id=owner_id,
                commit=False,
            ),
            post_commit_trigger_type=post_commit_trigger_type,
            intelligence_trigger_type="customer_activity_created",
            actor_id=actor_id,
            durable_work_policy=CustomerActivityDurableWorkPolicy.ALWAYS,
            before_commit=before_commit,
        )

    def update(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        obj_in: CustomerActivityUpdate,
        post_commit_trigger_type: str,
        actor_id: str | None,
    ) -> CustomerActivityWriteResult:
        return self._write(
            db,
            mutate=lambda: self.activity_crud.update(db, activity, obj_in, commit=False),
            post_commit_trigger_type=post_commit_trigger_type,
            intelligence_trigger_type="customer_activity_updated",
            actor_id=actor_id,
            durable_work_policy=CustomerActivityDurableWorkPolicy.ON_REVISION_CHANGE,
            previous_revision=int(activity.post_commit_revision or 1),
        )

    def update_next_follow_time(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        next_follow_time: datetime | None,
        post_commit_trigger_type: str,
        actor_id: str | None,
        mark_effectiveness_generating: bool = True,
    ) -> CustomerActivityWriteResult:
        def mutate() -> CustomerActivity:
            updated = self.activity_crud.update_next_time(
                db,
                activity,
                next_follow_time,
                commit=False,
            )
            if mark_effectiveness_generating:
                self.activity_crud.update_effectiveness_status(
                    db,
                    int(updated.id),
                    "GENERATING",
                    commit=False,
                )
            return updated

        return self._write(
            db,
            mutate=mutate,
            post_commit_trigger_type=post_commit_trigger_type,
            intelligence_trigger_type="customer_activity_updated",
            actor_id=actor_id,
            durable_work_policy=CustomerActivityDurableWorkPolicy.ON_REVISION_CHANGE,
            previous_revision=int(activity.post_commit_revision or 1),
        )

    def persist_structured_content(
        self,
        db: Session,
        *,
        activity_id: int,
        team_id: int,
        title: str | None,
        content_json: dict,
        summary: str | None,
        next_action: str | None,
        next_follow_time: datetime | None,
        next_follow_time_source: str | None,
        post_commit_trigger_type: str,
        actor_id: str | None,
    ) -> CustomerActivityWriteResult:
        current = self.activity_crud.get_by_id(db, activity_id, team_id)
        if current is None:
            raise ValueError("客户活动不存在")
        previous_revision = int(current.post_commit_revision or 1)

        def mutate() -> CustomerActivity:
            updated = self.activity_crud.update_processed_content(
                db,
                activity_id,
                title=title,
                content_json=content_json,
                summary=summary,
                next_action=next_action,
                next_follow_time=next_follow_time,
                next_follow_time_source=next_follow_time_source,
                commit=False,
            )
            if updated is None or int(updated.team_id) != int(team_id):
                raise ValueError("客户活动不存在")
            self.activity_crud.update_effectiveness_status(
                db,
                activity_id,
                "GENERATING",
                commit=False,
            )
            return updated

        return self._write(
            db,
            mutate=mutate,
            post_commit_trigger_type=post_commit_trigger_type,
            intelligence_trigger_type="customer_activity_updated",
            actor_id=actor_id,
            durable_work_policy=CustomerActivityDurableWorkPolicy.ALWAYS,
            previous_revision=previous_revision,
        )

    def kick(self, result: CustomerActivityWriteResult, *, include_post_commit: bool = True) -> None:
        """Kick already-committed work without making process liveness a correctness dependency."""

        if include_post_commit and result.post_commit_job is not None:
            self.post_commit_job_service.kick(result.post_commit_job)
        if result.customer_intelligence_request is not None:
            self.intelligence_refresh_service.kick_committed_event_refresh(result.customer_intelligence_request)

    def _write(
        self,
        db: Session,
        *,
        mutate: Callable[[], CustomerActivity],
        post_commit_trigger_type: str,
        intelligence_trigger_type: str,
        actor_id: str | None,
        durable_work_policy: CustomerActivityDurableWorkPolicy,
        previous_revision: int | None = None,
        before_commit: CustomerActivityBeforeCommit | None = None,
    ) -> CustomerActivityWriteResult:
        try:
            activity = mutate()
            activity_revision = int(activity.post_commit_revision or 1)
            if previous_revision is not None and activity_revision != previous_revision:
                self.confirmation_cleanup_service.cancel_pending_cases_for_source_activity(
                    db,
                    team_id=int(activity.team_id),
                    source_activity_id=int(activity.id),
                    actor_id=actor_id,
                    reason=FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_REVISION_SUPERSEDED,
                    commit=False,
                )
            should_enqueue = (
                durable_work_policy == CustomerActivityDurableWorkPolicy.ALWAYS
                or previous_revision is None
                or activity_revision != previous_revision
            )
            post_commit_job = None
            intelligence_request = None
            if should_enqueue:
                post_commit_job = self.post_commit_job_service.enqueue_in_transaction(
                    db,
                    activity=activity,
                    trigger_type=post_commit_trigger_type,
                    actor_id=actor_id,
                )
                intelligence_request = self._enqueue_customer_intelligence(
                    db,
                    activity=activity,
                    trigger_type=intelligence_trigger_type,
                )
            result = CustomerActivityWriteResult(
                activity=activity,
                activity_revision=activity_revision,
                post_commit_job=post_commit_job,
                customer_intelligence_request=intelligence_request,
            )
            if before_commit is not None:
                before_commit(result)
            db.commit()
            db.refresh(activity)
            return result
        except Exception:
            db.rollback()
            raise

    def _enqueue_customer_intelligence(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        trigger_type: str,
    ) -> CustomerIntelligenceCommittedEventRequest | None:
        event = self.intelligence_event_service.from_customer_activity(
            activity,
            trigger_type=trigger_type,
        )
        if event is None:
            return None
        return self.intelligence_refresh_service.enqueue_committed_event_refresh(
            db,
            event=event,
            scope="brief",
        )


customer_activity_write_service = CustomerActivityWriteService()
