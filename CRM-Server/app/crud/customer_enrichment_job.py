"""Persistence lifecycle for durable customer-enrichment jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.schemas.system_recovery import CustomerEnrichmentJobRecoveryCandidate
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobStatus,
    CustomerEnrichmentPurpose,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


_TERMINAL = {
    CustomerEnrichmentJobStatus.COMPLETED.value,
    CustomerEnrichmentJobStatus.SKIPPED.value,
    CustomerEnrichmentJobStatus.EXHAUSTED.value,
}
_RECOVERABLE = {
    CustomerEnrichmentJobStatus.QUEUED.value,
    CustomerEnrichmentJobStatus.RUNNING.value,
    CustomerEnrichmentJobStatus.RETRY_PENDING.value,
}


class CustomerEnrichmentJobCRUD:
    def ensure(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        purpose: str,
        plan_version: str,
        requested_fields: list[str],
        available_at: datetime,
        profile_gate_deadline_at: datetime | None,
        max_attempts: int,
        commit: bool = True,
    ) -> CustomerEnrichmentJob:
        existing = self.get_by_identity(
            db,
            team_id=team_id,
            customer_id=customer_id,
            plan_version=plan_version,
        )
        if existing is not None:
            return existing

        run_id = uuid4().hex
        candidate = CustomerEnrichmentJob(
            team_id=team_id,
            customer_id=customer_id,
            purpose=purpose,
            plan_version=plan_version,
            requested_fields_json=list(requested_fields),
            status=CustomerEnrichmentJobStatus.QUEUED.value,
            available_at=available_at,
            profile_gate_deadline_at=profile_gate_deadline_at,
            attempt_count=0,
            max_attempts=max(1, max_attempts),
            run_id=run_id,
            graph_thread_id=f"customer_enrichment:{team_id}:{customer_id}:{plan_version}:{run_id}",
            requeue_count=0,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self.get_by_identity(
                db,
                team_id=team_id,
                customer_id=customer_id,
                plan_version=plan_version,
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
        customer_id: int,
        plan_version: str,
    ) -> CustomerEnrichmentJob | None:
        return (
            db.query(CustomerEnrichmentJob)
            .filter(
                CustomerEnrichmentJob.team_id == team_id,
                CustomerEnrichmentJob.customer_id == customer_id,
                CustomerEnrichmentJob.plan_version == plan_version,
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
    ) -> CustomerEnrichmentJob | None:
        query = db.query(CustomerEnrichmentJob).filter(
            CustomerEnrichmentJob.team_id == team_id,
            CustomerEnrichmentJob.public_id == public_id,
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
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status in _TERMINAL:
            return None

        attempt_limit = max(1, int(job.max_attempts or 1))
        attempt_count = max(0, int(job.attempt_count or 0))
        if attempt_count >= attempt_limit:
            return None

        if job.status == CustomerEnrichmentJobStatus.QUEUED.value:
            claimable = job.available_at <= resolved_now
        elif job.status == CustomerEnrichmentJobStatus.RETRY_PENDING.value:
            claimable = job.next_attempt_at is not None and job.next_attempt_at <= resolved_now
        elif job.status == CustomerEnrichmentJobStatus.RUNNING.value:
            claimable = (
                not job.lease_token
                or job.lease_expires_at is None
                or job.lease_expires_at <= resolved_now
            )
        else:
            claimable = False
        if not claimable:
            return None

        job.status = CustomerEnrichmentJobStatus.RUNNING.value
        job.attempt_count = min(attempt_count + 1, attempt_limit)
        job.started_at = job.started_at or resolved_now
        job.finished_at = None
        job.next_attempt_at = None
        job.error_message = None
        job.lease_token = lease_token
        job.lease_expires_at = lease_expires_at
        self._persist(db, job, commit=commit)
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
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None

        job.status = (
            CustomerEnrichmentJobStatus.SKIPPED.value
            if skipped
            else CustomerEnrichmentJobStatus.COMPLETED.value
        )
        job.result_json = result_json
        job.error_message = None
        job.next_attempt_at = None
        job.finished_at = resolved_now
        job.first_attempt_finished_at = job.first_attempt_finished_at or resolved_now
        self._clear_lease(job)
        self._persist(db, job, commit=commit)
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
        result_json: dict[str, object],
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None

        job.status = CustomerEnrichmentJobStatus.RETRY_PENDING.value
        job.result_json = result_json
        job.error_message = error_message[:4000]
        job.next_attempt_at = next_attempt_at
        job.finished_at = None
        job.first_attempt_finished_at = job.first_attempt_finished_at or resolved_now
        self._clear_lease(job)
        self._persist(db, job, commit=commit)
        return job

    def mark_exhausted_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        lease_token: str,
        error_message: str,
        result_json: dict[str, object],
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None

        job.status = CustomerEnrichmentJobStatus.EXHAUSTED.value
        job.result_json = result_json
        job.error_message = error_message[:4000]
        job.next_attempt_at = None
        job.finished_at = resolved_now
        job.first_attempt_finished_at = job.first_attempt_finished_at or resolved_now
        self._clear_lease(job)
        self._persist(db, job, commit=commit)
        return job

    def requeue_exhausted(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        available_at: datetime,
        now: datetime | None = None,
        commit: bool = True,
    ) -> CustomerEnrichmentJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status != CustomerEnrichmentJobStatus.EXHAUSTED.value:
            return None

        previous_terminal = dict(job.result_json or {})
        job.status = CustomerEnrichmentJobStatus.QUEUED.value
        job.available_at = available_at
        job.attempt_count = 0
        job.next_attempt_at = None
        job.error_message = None
        job.started_at = None
        job.finished_at = None
        job.first_attempt_finished_at = None
        job.profile_refresh_request_id = None
        job.profile_refresh_enqueued_at = None
        job.requeue_count = int(job.requeue_count or 0) + 1
        job.result_json = {"previous_terminal": previous_terminal}
        job.updated_time = resolved_now
        self._clear_lease(job)
        self._persist(db, job, commit=commit)
        return job

    def list_system_recovery_candidates(
        self,
        db: Session,
        *,
        initial_limit: int,
        backfill_limit: int,
        now: datetime | None = None,
    ) -> list[CustomerEnrichmentJobRecoveryCandidate]:
        resolved_now = now or business_now()
        candidates: list[CustomerEnrichmentJobRecoveryCandidate] = []
        quotas = (
            (CustomerEnrichmentPurpose.INITIAL_CREATION.value, max(0, initial_limit)),
            (CustomerEnrichmentPurpose.HISTORICAL_BACKFILL.value, max(0, backfill_limit)),
        )
        for purpose, limit in quotas:
            if limit == 0:
                continue
            rows = (
                db.query(
                    CustomerEnrichmentJob.team_id,
                    CustomerEnrichmentJob.public_id,
                    CustomerEnrichmentJob.purpose,
                )
                .filter(
                    CustomerEnrichmentJob.purpose == purpose,
                    self._recoverable_predicate(resolved_now),
                )
                .order_by(
                    CustomerEnrichmentJob.available_at.asc(),
                    CustomerEnrichmentJob.next_attempt_at.asc(),
                    CustomerEnrichmentJob.created_time.asc(),
                    CustomerEnrichmentJob.id.asc(),
                )
                .limit(limit)
                .all()
            )
            candidates.extend(
                CustomerEnrichmentJobRecoveryCandidate(
                    team_id=int(row.team_id),
                    job_public_id=str(row.public_id),
                    purpose=str(row.purpose),
                )
                for row in rows
            )
        return candidates

    @staticmethod
    def _recoverable_predicate(now: datetime):
        due_queued = and_(
            CustomerEnrichmentJob.status == CustomerEnrichmentJobStatus.QUEUED.value,
            CustomerEnrichmentJob.available_at <= now,
        )
        due_retry = and_(
            CustomerEnrichmentJob.status == CustomerEnrichmentJobStatus.RETRY_PENDING.value,
            CustomerEnrichmentJob.next_attempt_at.is_not(None),
            CustomerEnrichmentJob.next_attempt_at <= now,
        )
        expired_running = and_(
            CustomerEnrichmentJob.status == CustomerEnrichmentJobStatus.RUNNING.value,
            or_(
                CustomerEnrichmentJob.lease_token.is_(None),
                CustomerEnrichmentJob.lease_expires_at.is_(None),
                CustomerEnrichmentJob.lease_expires_at <= now,
            ),
        )
        return and_(
            CustomerEnrichmentJob.status.in_(_RECOVERABLE),
            CustomerEnrichmentJob.attempt_count < CustomerEnrichmentJob.max_attempts,
            or_(due_queued, due_retry, expired_running),
        )

    @staticmethod
    def _owns_running_lease(job: CustomerEnrichmentJob | None, lease_token: str) -> bool:
        return bool(
            job is not None
            and job.status == CustomerEnrichmentJobStatus.RUNNING.value
            and job.lease_token
            and job.lease_token == lease_token
        )

    @staticmethod
    def _clear_lease(job: CustomerEnrichmentJob) -> None:
        job.lease_token = None
        job.lease_expires_at = None

    @staticmethod
    def _persist(db: Session, job: CustomerEnrichmentJob, *, commit: bool) -> None:
        db.add(job)
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()


customer_enrichment_job_crud = CustomerEnrichmentJobCRUD()
