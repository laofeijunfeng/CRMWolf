"""Transactional application seam for customer-activity writes.

Every activity revision that can affect downstream semantics is committed with
its durable post-commit job and canonical customer-intelligence run. Immediate
execution is deliberately outside this module; recovery owns correctness while
callers may kick the returned requests after commit for low latency.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from app.crud.customer_activity import CustomerActivityCRUD, customer_activity_crud
from app.crud.customer_activity_ai_job import CustomerActivityAIJobCRUD, customer_activity_ai_job_crud
from app.crud.customer_opportunity_suggestion_job import (
    CustomerOpportunitySuggestionJobCRUD,
    customer_opportunity_suggestion_job_crud,
)
from app.services.customer_opportunity_suggestion_job_service import (
    CustomerOpportunitySuggestionJobRequest,
    CustomerOpportunitySuggestionJobService,
    customer_opportunity_suggestion_job_service,
)
from app.crud.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJobCRUD,
    customer_activity_post_commit_job_crud,
)
from app.services.customer_activity_ai_job_service import (
    CustomerActivityAIJobRequest,
    CustomerActivityAIJobService,
    customer_activity_ai_job_service,
)
from app.services.customer_activity_contracts import (
    CustomerActivityEffectivenessStatus,
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
)
from app.services.customer_activity_field_provenance import (
    can_apply_ai_extracted_value,
)
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

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.customer_activity import CustomerActivity
    from app.schemas.customer_activity import CustomerActivityCreate


@dataclass(frozen=True)
class CustomerActivityFinalization:
    """Canonical structured content and the one final persisted score."""

    title: str | None
    content_json: dict
    summary: str | None
    next_action: str | None
    next_action_source: str | None
    next_follow_time: datetime | None
    next_follow_time_source: str | None
    effectiveness_score: int
    effectiveness_is_valid: bool
    effectiveness_reason: str
    effectiveness_detail_json: str | None


@dataclass(frozen=True)
class CustomerActivityWriteResult:
    activity: CustomerActivity
    activity_revision: int
    post_commit_job: CustomerActivityPostCommitJobRequest | None
    customer_intelligence_request: CustomerIntelligenceCommittedEventRequest | None
    ai_job: CustomerActivityAIJobRequest | None = None
    opportunity_suggestion_job: CustomerOpportunitySuggestionJobRequest | None = None


@dataclass(frozen=True)
class CustomerActivityDeleteResult:
    activity_id: int
    customer_intelligence_request: CustomerIntelligenceCommittedEventRequest | None


class CustomerActivityDurableWorkPolicy(StrEnum):
    ALWAYS = "ALWAYS"
    ON_REVISION_CHANGE = "ON_REVISION_CHANGE"


CustomerActivityBeforeCommit = Callable[[CustomerActivityWriteResult], None]


class CustomerActivityFinalizationError(ValueError):
    """Base error for deterministic AI-job finalization races."""


class CustomerActivitySourceDeletedError(CustomerActivityFinalizationError):
    """The source activity no longer exists when finalization begins."""


class CustomerActivityRevisionSupersededError(CustomerActivityFinalizationError):
    """The queued activity revision is no longer current."""


class CustomerActivitySubmissionSourceError(CustomerActivityFinalizationError):
    """The source is not eligible for background AI finalization."""


class CustomerActivitySubmissionConflictError(CustomerActivityFinalizationError):
    """A submission id was reused with a different request or incomplete record."""


def _form_submission_fingerprint(*, obj_in: CustomerActivityCreate, customer_id: int, team_id: int) -> str:
    payload = obj_in.model_dump(mode="json")
    payload.pop("submission_id", None)
    payload.pop("submission_source", None)
    payload["customer_id"] = customer_id
    payload["team_id"] = team_id
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CustomerActivityWriteService:
    """Own the atomic activity-write/outbox transaction behind one interface."""

    def __init__(
        self,
        *,
        activity_crud: CustomerActivityCRUD | None = None,
        ai_job_crud: CustomerActivityAIJobCRUD | None = None,
        post_commit_job_crud: CustomerActivityPostCommitJobCRUD | None = None,
        opportunity_suggestion_job_crud: CustomerOpportunitySuggestionJobCRUD | None = None,
        opportunity_suggestion_job_service: CustomerOpportunitySuggestionJobService | None = None,
        ai_job_service: CustomerActivityAIJobService | None = None,
        post_commit_job_service: CustomerActivityPostCommitJobService | None = None,
        intelligence_event_service: CustomerIntelligenceEventService | None = None,
        intelligence_refresh_service: CustomerIntelligenceRefreshService | None = None,
        confirmation_cleanup_service: FollowUpTaskConfirmationCleanupService | None = None,
    ) -> None:
        self.activity_crud = activity_crud or customer_activity_crud
        self.ai_job_crud = ai_job_crud or customer_activity_ai_job_crud
        self.post_commit_job_crud = post_commit_job_crud or customer_activity_post_commit_job_crud
        self.opportunity_suggestion_job_crud = (
            opportunity_suggestion_job_crud or customer_opportunity_suggestion_job_crud
        )
        self.opportunity_suggestion_job_service = (
            opportunity_suggestion_job_service or customer_opportunity_suggestion_job_service
        )
        self.ai_job_service = ai_job_service or customer_activity_ai_job_service
        self.post_commit_job_service = post_commit_job_service or customer_activity_post_commit_job_service
        self.intelligence_event_service = intelligence_event_service or customer_intelligence_event_service
        self.intelligence_refresh_service = intelligence_refresh_service or customer_intelligence_refresh_service
        self.confirmation_cleanup_service = confirmation_cleanup_service or follow_up_task_confirmation_cleanup_service

    def create_pending_from_form(
        self,
        db: Session,
        *,
        obj_in: CustomerActivityCreate,
        customer_id: int,
        creator_id: str,
        team_id: int,
        operator_name: str | None = None,
        original_lead_id: int | None = None,
        owner_id: str | None = None,
        before_commit: CustomerActivityBeforeCommit | None = None,
    ) -> CustomerActivityWriteResult:
        """Save a form activity and its durable AI job without post-commit work."""

        submission_id = getattr(obj_in, "submission_id", None)
        submission_fingerprint = (
            _form_submission_fingerprint(obj_in=obj_in, customer_id=customer_id, team_id=team_id)
            if submission_id
            else None
        )
        if submission_id:
            existing = self.activity_crud.get_by_submission_id(
                db, team_id=team_id, submission_id=submission_id
            )
            if existing is not None:
                if (
                    existing.submission_source != CustomerActivitySubmissionSource.FORM.value
                    or existing.submission_fingerprint != submission_fingerprint
                ):
                    raise CustomerActivitySubmissionConflictError(
                        "submission_id 已被其他请求使用，不能复用。"
                    )
                ai_job = self.ai_job_crud.get_by_identity(
                    db,
                    team_id=team_id,
                    activity_id=int(existing.id),
                    activity_revision=int(existing.activity_revision or 1),
                )
                if ai_job is None:
                    raise CustomerActivitySubmissionConflictError(
                        "submission_id 对应的客户活动缺少原始 AIJob，不能安全重放。"
                    )
                return CustomerActivityWriteResult(
                    activity=existing,
                    activity_revision=int(existing.activity_revision or 1),
                    post_commit_job=None,
                    customer_intelligence_request=None,
                    ai_job=CustomerActivityAIJobRequest(
                        job_public_id=ai_job.public_id,
                        team_id=team_id,
                    ),
                )

        try:
            activity = self.activity_crud.create(
                db=db,
                obj_in=obj_in,
                customer_id=customer_id,
                creator_id=creator_id,
                team_id=team_id,
                operator_name=operator_name,
                original_lead_id=original_lead_id,
                owner_id=owner_id,
                submission_source=CustomerActivitySubmissionSource.FORM.value,
                submission_id=submission_id,
                submission_fingerprint=submission_fingerprint,
                commit=False,
            )
            activity.processing_status = CustomerActivityProcessingStatus.PENDING.value
            activity.processing_error = None
            activity.processed_at = None
            activity.effectiveness_status = CustomerActivityEffectivenessStatus.PENDING.value
            activity.effectiveness_score = None
            activity.effectiveness_is_valid = None
            activity.effectiveness_reason = None
            activity.effectiveness_detail_json = None
            activity.effectiveness_evaluated_time = None
            activity.effectiveness_error_message = None
            ai_job = self.ai_job_service.enqueue_in_transaction(db, activity=activity)
            result = CustomerActivityWriteResult(
                activity=activity,
                activity_revision=int(activity.activity_revision or 1),
                post_commit_job=None,
                customer_intelligence_request=None,
                ai_job=ai_job,
            )
            if before_commit is not None:
                before_commit(result)
            db.commit()
            db.refresh(activity)
            return result
        except Exception:
            db.rollback()
            raise

    def create_final_from_agent(
        self,
        db: Session,
        *,
        obj_in: CustomerActivityCreate,
        finalization: CustomerActivityFinalization,
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
        """Write an Agent-finalized activity once, without creating an AI job."""

        if finalization.effectiveness_score < 60 or not finalization.effectiveness_is_valid:
            raise ValueError("Agent 最终评分未通过，不能写入客户活动")

        def mutate() -> CustomerActivity:
            activity = self.activity_crud.create(
                db=db,
                obj_in=obj_in,
                customer_id=customer_id,
                creator_id=creator_id,
                team_id=team_id,
                operator_name=operator_name,
                original_lead_id=original_lead_id,
                owner_id=owner_id,
                submission_source=CustomerActivitySubmissionSource.AGENT.value,
                submission_id=getattr(obj_in, "submission_id", None),
                commit=False,
            )
            return self._apply_finalization(
                db,
                activity=activity,
                finalization=finalization,
                increment_revision=False,
            )

        return self._write(
            db,
            mutate=mutate,
            post_commit_trigger_type=post_commit_trigger_type,
            intelligence_trigger_type="customer_activity_created",
            actor_id=actor_id,
            durable_work_policy=CustomerActivityDurableWorkPolicy.ALWAYS,
            enqueue_opportunity_suggestion=True,
            before_commit=before_commit,
        )

    def finalize_pending_from_ai(
        self,
        db: Session,
        *,
        activity_id: int,
        team_id: int,
        expected_activity_revision: int,
        ai_job_public_id: str,
        lease_token: str,
        finalization: CustomerActivityFinalization,
        post_commit_trigger_type: str,
        actor_id: str | None,
    ) -> CustomerActivityWriteResult:
        """Atomically finalize one form activity and complete its leased AI job."""

        current = self.activity_crud.get_by_id(db, activity_id, team_id)
        if current is None:
            raise CustomerActivitySourceDeletedError("客户活动不存在")
        if current.submission_source not in {
            CustomerActivitySubmissionSource.FORM.value,
            CustomerActivitySubmissionSource.CUTOVER_MIGRATION.value,
        }:
            raise CustomerActivitySubmissionSourceError(
                "仅页面表单活动或切换迁移活动允许由 AIJob 最终化"
            )
        if int(current.activity_revision or 1) != expected_activity_revision:
            raise CustomerActivityRevisionSupersededError("客户活动修订号已变化")

        request = CustomerActivityAIJobRequest(job_public_id=ai_job_public_id, team_id=team_id)

        def mutate() -> CustomerActivity:
            return self._apply_finalization(
                db,
                activity=current,
                finalization=finalization,
                increment_revision=True,
            )

        def complete_ai_job(result: CustomerActivityWriteResult) -> None:
            self.ai_job_service.mark_completed_in_transaction(
                db,
                request=request,
                lease_token=lease_token,
                result_json={
                    "job_public_id": ai_job_public_id,
                    "activity_id": int(result.activity.id),
                    "execution_status": "COMPLETED",
                    "success": True,
                    "retryable": False,
                    "skip_reason": None,
                    "error": None,
                    "activity_revision": result.activity_revision,
                    "effectiveness_score": finalization.effectiveness_score,
                },
            )

        result = self._write(
            db,
            mutate=mutate,
            post_commit_trigger_type=post_commit_trigger_type,
            intelligence_trigger_type="customer_activity_ai_finalized",
            actor_id=actor_id,
            durable_work_policy=CustomerActivityDurableWorkPolicy.ALWAYS,
            previous_revision=expected_activity_revision,
            before_commit=complete_ai_job,
        )
        return replace(result, ai_job=request)


    def _apply_finalization(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        finalization: CustomerActivityFinalization,
        increment_revision: bool,
    ) -> CustomerActivity:
        next_action = finalization.next_action
        next_action_source = finalization.next_action_source
        if next_action is not None and not can_apply_ai_extracted_value(
            current_value=activity.next_action,
            current_source=getattr(activity, "next_action_source", None),
        ):
            next_action = None
            next_action_source = None

        next_follow_time = finalization.next_follow_time
        next_follow_time_source = finalization.next_follow_time_source
        if next_follow_time is not None and not can_apply_ai_extracted_value(
            current_value=activity.next_follow_time,
            current_source=getattr(activity, "next_follow_time_source", None),
        ):
            next_follow_time = None
            next_follow_time_source = None

        return self.activity_crud.apply_finalization(
            db,
            activity,
            title=finalization.title,
            content_json=finalization.content_json,
            summary=finalization.summary,
            next_action=next_action,
            next_action_source=next_action_source,
            next_follow_time=next_follow_time,
            next_follow_time_source=next_follow_time_source,
            effectiveness_score=finalization.effectiveness_score,
            effectiveness_is_valid=finalization.effectiveness_is_valid,
            effectiveness_reason=finalization.effectiveness_reason,
            effectiveness_detail_json=finalization.effectiveness_detail_json,
            increment_revision=increment_revision,
            commit=False,
        )

    def delete(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        actor_id: str | None,
    ) -> CustomerActivityDeleteResult:
        """Delete an activity and register its negative intelligence evidence.

        Deletion is a source mutation, not an API concern. The projection,
        tombstone, durable intelligence event, and commit therefore live
        behind the same application seam as create/update. The caller only
        needs to kick the returned request after this method succeeds.
        """

        from app.models.sales_commitment import FollowUpTaskProjectionTrigger
        from app.services.follow_up_task_projection_service import follow_up_task_projection_service

        activity_id = int(activity.id)
        try:
            follow_up_task_projection_service.run_activity_projection(
                db,
                activity_id=activity.id,
                activity_snapshot=activity,
                trigger_type=FollowUpTaskProjectionTrigger.ACTIVITY_DELETED,
                actor_id=actor_id,
                team_id=int(activity.team_id),
                commit=False,
            )
            intelligence_request = self._enqueue_customer_intelligence(
                db,
                activity=activity,
                trigger_type="customer_activity_deleted",
            )
            # Preserve durable task evidence and close every still-runnable
            # activity-owned job before hard-deleting the source row. This is
            # deliberately in the same transaction as the tombstone/delete.
            self.ai_job_crud.mark_unfinished_skipped_for_activity(
                db,
                team_id=int(activity.team_id),
                activity_id=activity_id,
                reason="SOURCE_ACTIVITY_DELETED",
                commit=False,
            )
            self.post_commit_job_crud.mark_unfinished_skipped_for_activity(
                db,
                team_id=int(activity.team_id),
                activity_id=activity_id,
                reason="SOURCE_ACTIVITY_DELETED",
                commit=False,
            )
            self.opportunity_suggestion_job_crud.mark_unfinished_skipped_for_activity(
                db,
                team_id=int(activity.team_id),
                activity_id=activity_id,
                reason="SOURCE_ACTIVITY_DELETED",
                commit=False,
            )
            self.activity_crud.delete(
                db,
                activity,
                commit=False,
                deleted_by=actor_id,
            )
            db.commit()
            return CustomerActivityDeleteResult(
                activity_id=activity_id,
                customer_intelligence_request=intelligence_request,
            )
        except Exception:
            db.rollback()
            raise

    def kick_delete(self, result: CustomerActivityDeleteResult) -> None:
        """Kick intelligence work only after the delete transaction commits."""

        if result.customer_intelligence_request is not None:
            self.intelligence_refresh_service.kick_committed_event_refresh(
                result.customer_intelligence_request
            )

    def kick(self, result: CustomerActivityWriteResult, *, include_post_commit: bool = True) -> None:
        """Kick already-committed work without making process liveness a correctness dependency."""

        if result.ai_job is not None:
            self.ai_job_service.kick(result.ai_job)
        if result.opportunity_suggestion_job is not None:
            self.opportunity_suggestion_job_service.kick(result.opportunity_suggestion_job)
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
        enqueue_opportunity_suggestion: bool = False,
        before_commit: CustomerActivityBeforeCommit | None = None,
    ) -> CustomerActivityWriteResult:
        try:
            activity = mutate()
            activity_revision = int(activity.activity_revision or 1)
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
            opportunity_suggestion_job = None
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
            if enqueue_opportunity_suggestion and str(getattr(activity, "submission_source", "")) == CustomerActivitySubmissionSource.AGENT.value:
                opportunity_suggestion_job = self._enqueue_opportunity_suggestion_safely(db, activity)
            result = CustomerActivityWriteResult(
                activity=activity,
                activity_revision=activity_revision,
                post_commit_job=post_commit_job,
                customer_intelligence_request=intelligence_request,
                opportunity_suggestion_job=opportunity_suggestion_job,
            )
            if before_commit is not None:
                before_commit(result)
            db.commit()
            db.refresh(activity)
            return result
        except Exception:
            db.rollback()
            raise

    def _enqueue_opportunity_suggestion_safely(
        self,
        db: Session,
        activity: CustomerActivity,
    ) -> CustomerOpportunitySuggestionJobRequest | None:
        """Register Agent-only suggestion work without making it activity-critical."""

        try:
            with db.begin_nested():
                return self.opportunity_suggestion_job_service.enqueue_in_transaction(
                    db, activity=activity
                )
        except Exception:
            # Activity, PostCommitJob and intelligence commitment must survive a
            # suggestion-outbox outage. A later reconciliation can enqueue the
            # missing Agent revision from the committed activity.
            logger.exception(
                "客户活动商机建议任务入队失败,不回滚活动: activity_id=%s team_id=%s",
                getattr(activity, "id", None),
                getattr(activity, "team_id", None),
            )
            return None

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
        try:
            # Customer intelligence is an asynchronous read model. Keep its
            # durable enqueue inside a savepoint so a missing/temporarily
            # unavailable intelligence table cannot roll back the activity
            # write or its task/commitment projection. Reconciliation repairs
            # the missed enqueue from the committed business state.
            with db.begin_nested():
                return self.intelligence_refresh_service.enqueue_committed_event_refresh(
                    db,
                    event=event,
                    scope="partial",
                )
        except Exception as exc:
            schedule_error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "客户活动客户智能事件入队失败,将由对账机制补偿: activity_id=%s team_id=%s customer_id=%s",
                getattr(activity, "id", None),
                getattr(activity, "team_id", None),
                getattr(activity, "customer_id", None),
            )
            return CustomerIntelligenceCommittedEventRequest(
                request_id=f"business-event-{event.trigger_type}-{event.event_key[:16]}",
                event=event,
                scope="partial",
                scheduled=False,
                kick_required=False,
                schedule_error=schedule_error,
            )


customer_activity_write_service = CustomerActivityWriteService()
