"""Persistence interface for durable customer-activity post-commit jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.models.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJob,
    CustomerActivityPostCommitJobStatus,
)
from app.schemas.system_recovery import CustomerActivityPostCommitRecoveryCandidate
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


class CustomerActivityPostCommitJobCRUD:
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
    ) -> CustomerActivityPostCommitJob:
        existing = self.get_by_identity(
            db,
            team_id=team_id,
            activity_id=activity_id,
            activity_revision=activity_revision,
            trigger_type=trigger_type,
        )
        if existing is not None:
            return existing
        run_id = uuid4().hex
        candidate = CustomerActivityPostCommitJob(
            team_id=team_id,
            activity_id=activity_id,
            activity_revision=activity_revision,
            trigger_type=trigger_type,
            actor_id=actor_id,
            status=CustomerActivityPostCommitJobStatus.QUEUED,
            run_id=run_id,
            graph_thread_id=(
                f"customer_activity_post_commit:{team_id}:{activity_id}:{trigger_type}:{activity_revision}:{run_id}"
            ),
            attempt_count=0,
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
                trigger_type=trigger_type,
            )
            if existing is None:
                raise
            return existing
        if commit:
            db.commit()
            db.refresh(candidate)
        return candidate

    def get_by_public_id(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        for_update: bool = False,
    ) -> CustomerActivityPostCommitJob | None:
        query = db.query(CustomerActivityPostCommitJob).filter(
            CustomerActivityPostCommitJob.team_id == team_id,
            CustomerActivityPostCommitJob.public_id == public_id,
        )
        if for_update:
            query = query.populate_existing().with_for_update()
        return query.one_or_none()

    def get_by_identity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        activity_revision: int,
        trigger_type: str,
    ) -> CustomerActivityPostCommitJob | None:
        return (
            db.query(CustomerActivityPostCommitJob)
            .filter(
                CustomerActivityPostCommitJob.team_id == team_id,
                CustomerActivityPostCommitJob.activity_id == activity_id,
                CustomerActivityPostCommitJob.activity_revision == activity_revision,
                CustomerActivityPostCommitJob.trigger_type == trigger_type,
            )
            .one_or_none()
        )

    def get_latest_by_activity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
    ) -> CustomerActivityPostCommitJob | None:
        return (
            db.query(CustomerActivityPostCommitJob)
            .filter(
                CustomerActivityPostCommitJob.team_id == team_id,
                CustomerActivityPostCommitJob.activity_id == activity_id,
            )
            .order_by(
                CustomerActivityPostCommitJob.activity_revision.desc(),
                CustomerActivityPostCommitJob.id.desc(),
            )
            .first()
        )

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
    ) -> CustomerActivityPostCommitJob | None:
        """Atomically acquire an execution lease for a due job.

        A live RUNNING lease is busy, not recoverable. Attempt count advances only
        after a successful claim, so concurrent workers do not consume retries.
        """

        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status in CustomerActivityPostCommitJobStatus.TERMINAL:
            return None
        if int(job.attempt_count or 0) >= max(1, max_attempts):
            return None
        claimable = job.status == CustomerActivityPostCommitJobStatus.QUEUED
        if job.status == CustomerActivityPostCommitJobStatus.FAILED:
            claimable = job.next_attempt_at is None or job.next_attempt_at <= resolved_now
        elif job.status == CustomerActivityPostCommitJobStatus.RUNNING:
            claimable = job.lease_expires_at is None or job.lease_expires_at <= resolved_now
        if not claimable:
            return None

        job.status = CustomerActivityPostCommitJobStatus.RUNNING
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.started_at = job.started_at or resolved_now
        job.finished_at = None
        job.next_attempt_at = None
        job.error_message = None
        job.lease_token = lease_token
        job.lease_expires_at = lease_expires_at
        db.add(job)
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def finalize_retries_exhausted(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        max_attempts: int,
        result_json: dict[str, object],
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerActivityPostCommitJob | None:
        """Persist the terminal state once no execution attempt remains.

        A live RUNNING lease still owns the outcome and cannot be dead-lettered
        by another worker. Expired leases and failed jobs are safe to finalize.
        """

        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None:
            return None
        if job.status in CustomerActivityPostCommitJobStatus.TERMINAL:
            return job
        if int(job.attempt_count or 0) < max(1, max_attempts):
            return None
        if (
            job.status == CustomerActivityPostCommitJobStatus.RUNNING
            and job.lease_token
            and job.lease_expires_at
            and job.lease_expires_at > resolved_now
        ):
            return None

        job.status = CustomerActivityPostCommitJobStatus.EXHAUSTED
        job.result_json = result_json
        job.next_attempt_at = None
        job.finished_at = resolved_now
        job.lease_token = None
        job.lease_expires_at = None
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
    ) -> CustomerActivityPostCommitJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = (
            CustomerActivityPostCommitJobStatus.SKIPPED if skipped else CustomerActivityPostCommitJobStatus.COMPLETED
        )
        job.result_json = result_json
        job.error_message = None
        job.next_attempt_at = None
        job.finished_at = business_now()
        job.lease_token = None
        job.lease_expires_at = None
        db.add(job)
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
    ) -> CustomerActivityPostCommitJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = CustomerActivityPostCommitJobStatus.EXHAUSTED
        job.result_json = result_json
        job.error_message = error_message[:4000]
        job.next_attempt_at = None
        job.finished_at = business_now()
        job.lease_token = None
        job.lease_expires_at = None
        db.add(job)
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def mark_failed_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        error_message: str,
        next_attempt_at: datetime | None,
        commit: bool = True,
    ) -> CustomerActivityPostCommitJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = CustomerActivityPostCommitJobStatus.FAILED
        job.error_message = error_message[:4000]
        job.next_attempt_at = next_attempt_at
        job.finished_at = None
        job.lease_token = None
        job.lease_expires_at = None
        db.add(job)
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

    def list_system_recovery_candidates(
        self,
        db: Session,
        *,
        max_attempts: int,
        limit: int,
        now: datetime | None = None,
    ) -> list[CustomerActivityPostCommitRecoveryCandidate]:
        """Privileged control-plane scan returning tenant routing identities only."""

        resolved_now = now or business_now()
        attempt_limit = max(1, max_attempts)
        expired_running = and_(
            CustomerActivityPostCommitJob.status == CustomerActivityPostCommitJobStatus.RUNNING,
            or_(
                CustomerActivityPostCommitJob.lease_expires_at.is_(None),
                CustomerActivityPostCommitJob.lease_expires_at <= resolved_now,
            ),
        )
        due_failed = and_(
            CustomerActivityPostCommitJob.status == CustomerActivityPostCommitJobStatus.FAILED,
            or_(
                CustomerActivityPostCommitJob.next_attempt_at.is_(None),
                CustomerActivityPostCommitJob.next_attempt_at <= resolved_now,
            ),
        )
        claimable = and_(
            CustomerActivityPostCommitJob.attempt_count < attempt_limit,
            or_(
                CustomerActivityPostCommitJob.status == CustomerActivityPostCommitJobStatus.QUEUED,
                expired_running,
                due_failed,
            ),
        )
        needs_terminalization = and_(
            CustomerActivityPostCommitJob.attempt_count >= attempt_limit,
            or_(
                CustomerActivityPostCommitJob.status == CustomerActivityPostCommitJobStatus.QUEUED,
                CustomerActivityPostCommitJob.status == CustomerActivityPostCommitJobStatus.FAILED,
                expired_running,
            ),
        )
        rows = (
            db.query(
                CustomerActivityPostCommitJob.team_id,
                CustomerActivityPostCommitJob.public_id,
            )
            .filter(or_(claimable, needs_terminalization))
            .order_by(CustomerActivityPostCommitJob.created_time.asc(), CustomerActivityPostCommitJob.id.asc())
            .limit(max(1, limit))
            .all()
        )
        return [
            CustomerActivityPostCommitRecoveryCandidate(
                team_id=int(row.team_id),
                job_public_id=str(row.public_id),
            )
            for row in rows
        ]

    @staticmethod
    def _owns_running_lease(job: CustomerActivityPostCommitJob | None, lease_token: str) -> bool:
        return bool(
            job is not None
            and job.status == CustomerActivityPostCommitJobStatus.RUNNING
            and job.lease_token
            and job.lease_token == lease_token
        )


customer_activity_post_commit_job_crud = CustomerActivityPostCommitJobCRUD()
