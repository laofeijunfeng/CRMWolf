"""Persistence interface for durable opportunity suggestion jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.schemas.system_recovery import CustomerOpportunitySuggestionJobRecoveryCandidate
from app.services.customer_activity_contracts import (
    CustomerActivitySubmissionSource,
    CustomerActivitySuggestionJobStatus,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

_TERMINAL = {
    CustomerActivitySuggestionJobStatus.COMPLETED.value,
    CustomerActivitySuggestionJobStatus.SKIPPED.value,
    CustomerActivitySuggestionJobStatus.EXHAUSTED.value,
}


class CustomerOpportunitySuggestionJobCRUD:
    def enqueue(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        activity_revision: int,
        submission_source: str = CustomerActivitySubmissionSource.AGENT.value,
        commit: bool = True,
    ) -> CustomerOpportunitySuggestionJob:
        if submission_source != CustomerActivitySubmissionSource.AGENT.value:
            raise ValueError("商机建议任务仅允许由 Agent 活动创建")
        existing = self.get_by_identity(
            db,
            team_id=team_id,
            activity_id=activity_id,
            activity_revision=activity_revision,
        )
        if existing is not None:
            return existing

        run_id = uuid4().hex
        candidate = CustomerOpportunitySuggestionJob(
            team_id=team_id,
            activity_id=activity_id,
            activity_revision=activity_revision,
            submission_source=submission_source,
            status=CustomerActivitySuggestionJobStatus.QUEUED.value,
            attempt_count=0,
            run_id=run_id,
            graph_thread_id=(f"customer_opportunity_suggestion:{team_id}:{activity_id}:{activity_revision}:{run_id}"),
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self.get_by_identity(
                db,
                team_id=team_id,
                activity_id=activity_id,
                activity_revision=activity_revision,
            )
            if existing is None:
                raise
            return existing
        if commit:
            db.commit()
            db.refresh(candidate)
        return candidate

    def get_by_identity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        activity_revision: int,
    ) -> CustomerOpportunitySuggestionJob | None:
        return (
            db.query(CustomerOpportunitySuggestionJob)
            .filter(
                CustomerOpportunitySuggestionJob.team_id == team_id,
                CustomerOpportunitySuggestionJob.activity_id == activity_id,
                CustomerOpportunitySuggestionJob.activity_revision == activity_revision,
            )
            .one_or_none()
        )

    def get_by_public_id(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        for_update: bool = False,
    ) -> CustomerOpportunitySuggestionJob | None:
        query = db.query(CustomerOpportunitySuggestionJob).filter(
            CustomerOpportunitySuggestionJob.team_id == team_id,
            CustomerOpportunitySuggestionJob.public_id == public_id,
        )
        if for_update:
            query = query.populate_existing().with_for_update()
        return query.one_or_none()

    def claim_for_execution(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        lease_expires_at: datetime,
        max_attempts: int,
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerOpportunitySuggestionJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status in _TERMINAL or int(job.attempt_count or 0) >= max(1, max_attempts):
            return None
        claimable = job.status == CustomerActivitySuggestionJobStatus.QUEUED.value
        if job.status == CustomerActivitySuggestionJobStatus.RETRY_PENDING.value:
            claimable = job.next_attempt_at is None or job.next_attempt_at <= resolved_now
        elif job.status == CustomerActivitySuggestionJobStatus.RUNNING.value:
            claimable = job.lease_expires_at is None or job.lease_expires_at <= resolved_now
        if not claimable:
            return None

        job.status = CustomerActivitySuggestionJobStatus.RUNNING.value
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.started_at = job.started_at or resolved_now
        job.finished_at = None
        job.next_attempt_at = None
        job.error_message = None
        job.lease_token = lease_token
        job.lease_expires_at = lease_expires_at
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def mark_completed_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        result_json: dict[str, object],
        skipped: bool = False,
        commit: bool = True,
    ) -> CustomerOpportunitySuggestionJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = (
            CustomerActivitySuggestionJobStatus.SKIPPED.value
            if skipped
            else CustomerActivitySuggestionJobStatus.COMPLETED.value
        )
        job.result_json = result_json
        job.error_message = None
        job.next_attempt_at = None
        job.finished_at = business_now()
        job.lease_token = None
        job.lease_expires_at = None
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def mark_retry_pending_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        error_message: str,
        next_attempt_at: datetime,
        commit: bool = True,
    ) -> CustomerOpportunitySuggestionJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = CustomerActivitySuggestionJobStatus.RETRY_PENDING.value
        job.error_message = error_message[:4000]
        job.next_attempt_at = next_attempt_at
        job.finished_at = None
        job.lease_token = None
        job.lease_expires_at = None
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def mark_exhausted_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        result_json: dict[str, object],
        error_message: str,
        commit: bool = True,
    ) -> CustomerOpportunitySuggestionJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = CustomerActivitySuggestionJobStatus.EXHAUSTED.value
        job.result_json = result_json
        job.error_message = error_message[:4000]
        job.next_attempt_at = None
        job.finished_at = business_now()
        job.lease_token = None
        job.lease_expires_at = None
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def mark_exhausted_if_attempts_exceeded(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        max_attempts: int,
        result_json: dict[str, object],
        error_message: str,
        commit: bool = True,
    ) -> CustomerOpportunitySuggestionJob | None:
        """Persist exhaustion discovered before a worker can claim a job.

        Recovery and replay can observe a job whose previous worker already
        consumed the final attempt.  That state must be terminalized in the
        database rather than merely returned to the caller, otherwise every
        recovery scan will rediscover the same job forever.
        """

        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status in _TERMINAL or int(job.attempt_count or 0) < max(1, max_attempts):
            return None
        job.status = CustomerActivitySuggestionJobStatus.EXHAUSTED.value
        job.result_json = result_json
        job.error_message = error_message[:4000]
        job.next_attempt_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.finished_at = job.finished_at or business_now()
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def mark_unfinished_skipped_for_activity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        reason: str,
        commit: bool = True,
    ) -> int:
        jobs = (
            db.query(CustomerOpportunitySuggestionJob)
            .filter(
                CustomerOpportunitySuggestionJob.team_id == team_id,
                CustomerOpportunitySuggestionJob.activity_id == activity_id,
                CustomerOpportunitySuggestionJob.status.notin_(_TERMINAL),
            )
            .with_for_update()
            .all()
        )
        finished_at = business_now()
        for job in jobs:
            result_json = dict(job.result_json or {})
            result_json["skip_reason"] = reason
            result_json["source_activity_deleted"] = True
            if job.error_message:
                result_json.setdefault("previous_error", job.error_message)
            job.status = CustomerActivitySuggestionJobStatus.SKIPPED.value
            job.result_json = result_json
            job.error_message = reason
            job.next_attempt_at = None
            job.lease_token = None
            job.lease_expires_at = None
            job.finished_at = finished_at
            db.add(job)
        if commit:
            db.commit()
        else:
            db.flush()
        return len(jobs)

    def list_system_recovery_candidates(
        self,
        db: Session,
        *,
        max_attempts: int,
        limit: int,
        now: datetime | None = None,
    ) -> list[CustomerOpportunitySuggestionJobRecoveryCandidate]:
        resolved_now = now or business_now()
        attempt_limit = max(1, max_attempts)
        expired_running = and_(
            CustomerOpportunitySuggestionJob.status == CustomerActivitySuggestionJobStatus.RUNNING.value,
            or_(
                CustomerOpportunitySuggestionJob.lease_expires_at.is_(None),
                CustomerOpportunitySuggestionJob.lease_expires_at <= resolved_now,
            ),
        )
        due_retry = and_(
            CustomerOpportunitySuggestionJob.status == CustomerActivitySuggestionJobStatus.RETRY_PENDING.value,
            or_(
                CustomerOpportunitySuggestionJob.next_attempt_at.is_(None),
                CustomerOpportunitySuggestionJob.next_attempt_at <= resolved_now,
            ),
        )
        recoverable = or_(
            CustomerOpportunitySuggestionJob.status == CustomerActivitySuggestionJobStatus.QUEUED.value,
            expired_running,
            due_retry,
        )
        rows = (
            db.query(CustomerOpportunitySuggestionJob.team_id, CustomerOpportunitySuggestionJob.public_id)
            .filter(recoverable)
            .order_by(
                (CustomerOpportunitySuggestionJob.attempt_count >= attempt_limit).desc(),
                CustomerOpportunitySuggestionJob.created_time.asc(),
                CustomerOpportunitySuggestionJob.id.asc(),
            )
            .limit(max(1, limit))
            .all()
        )
        return [
            CustomerOpportunitySuggestionJobRecoveryCandidate(
                team_id=int(row.team_id),
                job_public_id=str(row.public_id),
            )
            for row in rows
        ]

    @staticmethod
    def _owns_running_lease(job: CustomerOpportunitySuggestionJob | None, lease_token: str) -> bool:
        return bool(
            job is not None
            and job.status == CustomerActivitySuggestionJobStatus.RUNNING.value
            and job.lease_token
            and job.lease_token == lease_token
        )


customer_opportunity_suggestion_job_crud = CustomerOpportunitySuggestionJobCRUD()
