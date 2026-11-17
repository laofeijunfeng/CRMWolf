"""Persistence operations for Assistant 2.0 projection jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.models.assistant_follow_up_projection_job import (
    AssistantFollowUpProjectionJob,
    AssistantFollowUpProjectionJobStatus,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


class AssistantFollowUpProjectionJobCRUD:
    def enqueue(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        activity_revision: int,
        trigger_type: str,
        actor_id: str | None,
        commit: bool = True,
    ) -> AssistantFollowUpProjectionJob:
        existing = self.get_by_identity(
            db,
            team_id=team_id,
            activity_id=activity_id,
            activity_revision=activity_revision,
            trigger_type=trigger_type,
        )
        if existing is not None:
            return existing
        job = AssistantFollowUpProjectionJob(
            team_id=team_id,
            activity_id=activity_id,
            activity_revision=activity_revision,
            trigger_type=trigger_type,
            actor_id=actor_id,
            status=AssistantFollowUpProjectionJobStatus.QUEUED,
            attempt_count=0,
        )
        try:
            with db.begin_nested():
                db.add(job)
                db.flush()
        except IntegrityError:
            existing = self.get_by_identity(
                db,
                team_id=team_id,
                activity_id=activity_id,
                activity_revision=activity_revision,
                trigger_type=trigger_type,
            )
            if existing is None:
                raise
            return existing
        if commit:
            db.commit()
            db.refresh(job)
        return job

    def get_by_identity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        activity_revision: int,
        trigger_type: str,
    ) -> AssistantFollowUpProjectionJob | None:
        return (
            db.query(AssistantFollowUpProjectionJob)
            .filter(
                AssistantFollowUpProjectionJob.team_id == team_id,
                AssistantFollowUpProjectionJob.activity_id == activity_id,
                AssistantFollowUpProjectionJob.activity_revision == activity_revision,
                AssistantFollowUpProjectionJob.trigger_type == trigger_type,
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
    ) -> AssistantFollowUpProjectionJob | None:
        query = db.query(AssistantFollowUpProjectionJob).filter(
            AssistantFollowUpProjectionJob.team_id == team_id,
            AssistantFollowUpProjectionJob.public_id == public_id,
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
    ) -> AssistantFollowUpProjectionJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status in AssistantFollowUpProjectionJobStatus.TERMINAL:
            return None
        if int(job.attempt_count or 0) >= max(1, max_attempts):
            return None
        claimable = job.status == AssistantFollowUpProjectionJobStatus.QUEUED
        if job.status == AssistantFollowUpProjectionJobStatus.FAILED:
            claimable = job.next_attempt_at is None or job.next_attempt_at <= resolved_now
        elif job.status == AssistantFollowUpProjectionJobStatus.RUNNING:
            claimable = job.lease_expires_at is None or job.lease_expires_at <= resolved_now
        if not claimable:
            return None
        job.status = AssistantFollowUpProjectionJobStatus.RUNNING
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.lease_token = lease_token
        job.lease_expires_at = lease_expires_at
        job.started_at = job.started_at or resolved_now
        job.next_attempt_at = None
        db.add(job)
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
    ) -> AssistantFollowUpProjectionJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = (
            AssistantFollowUpProjectionJobStatus.SKIPPED
            if skipped
            else AssistantFollowUpProjectionJobStatus.COMPLETED
        )
        job.result_json = result_json
        job.error_message = None
        job.lease_token = None
        job.lease_expires_at = None
        job.next_attempt_at = None
        job.finished_at = business_now()
        db.add(job)
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def mark_exhausted_without_lease(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        result_json: dict[str, object],
        error_message: str,
    ) -> AssistantFollowUpProjectionJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status in AssistantFollowUpProjectionJobStatus.TERMINAL:
            return job
        if (
            job.status == AssistantFollowUpProjectionJobStatus.RUNNING
            and job.lease_token
            and job.lease_expires_at
            and job.lease_expires_at > business_now()
        ):
            return None
        job.status = AssistantFollowUpProjectionJobStatus.EXHAUSTED
        job.result_json = result_json
        job.error_message = error_message
        job.next_attempt_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.finished_at = business_now()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job


    def mark_failed_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        error_message: str,
        next_attempt_at: datetime,
    ) -> AssistantFollowUpProjectionJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = AssistantFollowUpProjectionJobStatus.FAILED
        job.error_message = error_message
        job.lease_token = None
        job.lease_expires_at = None
        job.next_attempt_at = next_attempt_at
        db.add(job)
        db.commit()
        db.refresh(job)
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
    ) -> AssistantFollowUpProjectionJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = AssistantFollowUpProjectionJobStatus.EXHAUSTED
        job.result_json = result_json
        job.error_message = error_message
        job.lease_token = None
        job.lease_expires_at = None
        job.next_attempt_at = None
        job.finished_at = business_now()
        db.add(job)
        db.commit()
        db.refresh(job)
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
            db.query(AssistantFollowUpProjectionJob)
            .filter(
                AssistantFollowUpProjectionJob.team_id == team_id,
                AssistantFollowUpProjectionJob.activity_id == activity_id,
                AssistantFollowUpProjectionJob.status.notin_(AssistantFollowUpProjectionJobStatus.TERMINAL),
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
            job.status = AssistantFollowUpProjectionJobStatus.SKIPPED
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
    ) -> list[AssistantFollowUpProjectionJob]:
        resolved_now = now or business_now()
        attempt_limit = max(1, max_attempts)
        expired_running = and_(
            AssistantFollowUpProjectionJob.status == AssistantFollowUpProjectionJobStatus.RUNNING,
            or_(
                AssistantFollowUpProjectionJob.lease_expires_at.is_(None),
                AssistantFollowUpProjectionJob.lease_expires_at <= resolved_now,
            ),
        )
        due_failed = and_(
            AssistantFollowUpProjectionJob.status == AssistantFollowUpProjectionJobStatus.FAILED,
            or_(
                AssistantFollowUpProjectionJob.next_attempt_at.is_(None),
                AssistantFollowUpProjectionJob.next_attempt_at <= resolved_now,
            ),
        )
        claimable = or_(
            AssistantFollowUpProjectionJob.status == AssistantFollowUpProjectionJobStatus.QUEUED,
            expired_running,
            due_failed,
        )
        return (
            db.query(AssistantFollowUpProjectionJob)
            .filter(claimable, AssistantFollowUpProjectionJob.attempt_count <= attempt_limit)
            .order_by(AssistantFollowUpProjectionJob.created_time.asc(), AssistantFollowUpProjectionJob.id.asc())
            .limit(max(1, limit))
            .all()
        )

    @staticmethod
    def _owns_running_lease(job: AssistantFollowUpProjectionJob | None, lease_token: str) -> bool:
        now = business_now()
        return bool(
            job
            and job.status == AssistantFollowUpProjectionJobStatus.RUNNING
            and job.lease_token == lease_token
            and job.lease_expires_at is not None
            and job.lease_expires_at > now
        )


assistant_follow_up_projection_job_crud = AssistantFollowUpProjectionJobCRUD()
