"""Persistence interface for durable outbound notification jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from app.models.outbound_notification_job import (
    OutboundNotificationJob,
    OutboundNotificationJobStatus,
)
from app.schemas.system_recovery import OutboundNotificationJobRecoveryCandidate
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session


class OutboundNotificationJobCRUD:
    def enqueue(
        self,
        db: Session,
        *,
        team_id: int,
        event_type: str,
        idempotency_key: str,
        recipient_user_ids: list[int],
        business_type: str,
        business_id: int,
        approval_id: int | None = None,
        node_id: int | None = None,
        actor_id: str | None = None,
        payload_json: dict[str, object] | None = None,
        commit: bool = True,
    ) -> OutboundNotificationJob:
        existing = self.get_by_idempotency_key(
            db,
            team_id=team_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing
        candidate = OutboundNotificationJob(
            team_id=team_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            approval_id=approval_id,
            node_id=node_id,
            business_type=business_type,
            business_id=business_id,
            actor_id=actor_id,
            recipient_user_ids=list(recipient_user_ids),
            payload_json=payload_json or {},
            status=OutboundNotificationJobStatus.QUEUED,
            attempt_count=0,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self.get_by_idempotency_key(
                db,
                team_id=team_id,
                idempotency_key=idempotency_key,
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
    ) -> OutboundNotificationJob | None:
        query = db.query(OutboundNotificationJob).filter(
            OutboundNotificationJob.team_id == team_id,
            OutboundNotificationJob.public_id == public_id,
        )
        if for_update:
            query = query.populate_existing().with_for_update()
        return query.one_or_none()

    def get_by_idempotency_key(
        self,
        db: Session,
        *,
        team_id: int,
        idempotency_key: str,
        for_update: bool = False,
    ) -> OutboundNotificationJob | None:
        query = db.query(OutboundNotificationJob).filter(
            OutboundNotificationJob.team_id == team_id,
            OutboundNotificationJob.idempotency_key == idempotency_key,
        )
        if for_update:
            query = query.populate_existing().with_for_update()
        return query.one_or_none()

    def reset_for_retry(
        self,
        db: Session,
        *,
        team_id: int,
        public_id: str,
        recipient_user_ids: list[int] | None = None,
        payload_json: dict[str, object] | None = None,
        commit: bool = True,
    ) -> OutboundNotificationJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None:
            return None
        job.status = OutboundNotificationJobStatus.QUEUED
        job.attempt_count = 0
        job.next_attempt_at = None
        job.lease_token = None
        job.lease_expires_at = None
        job.error_message = None
        job.result_json = None
        job.finished_at = None
        job.started_at = None
        if recipient_user_ids is not None:
            job.recipient_user_ids = list(recipient_user_ids)
        if payload_json is not None:
            job.payload_json = payload_json
        db.add(job)
        if commit:
            db.commit()
            db.refresh(job)
        else:
            db.flush()
        return job

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
    ) -> OutboundNotificationJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None or job.status in OutboundNotificationJobStatus.TERMINAL:
            return None
        if int(job.attempt_count or 0) >= max(1, max_attempts):
            return None
        claimable = job.status == OutboundNotificationJobStatus.QUEUED
        if job.status == OutboundNotificationJobStatus.FAILED:
            claimable = job.next_attempt_at is None or job.next_attempt_at <= resolved_now
        elif job.status == OutboundNotificationJobStatus.RUNNING:
            claimable = job.lease_expires_at is None or job.lease_expires_at <= resolved_now
        if not claimable:
            return None

        job.status = OutboundNotificationJobStatus.RUNNING
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
    ) -> OutboundNotificationJob | None:
        resolved_now = now or business_now()
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if job is None:
            return None
        if job.status in OutboundNotificationJobStatus.TERMINAL:
            return job
        if int(job.attempt_count or 0) < max(1, max_attempts):
            return None
        if (
            job.status == OutboundNotificationJobStatus.RUNNING
            and job.lease_token
            and job.lease_expires_at
            and job.lease_expires_at > resolved_now
        ):
            return None

        job.status = OutboundNotificationJobStatus.EXHAUSTED
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
    ) -> OutboundNotificationJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = (
            OutboundNotificationJobStatus.SKIPPED if skipped else OutboundNotificationJobStatus.COMPLETED
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
    ) -> OutboundNotificationJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = OutboundNotificationJobStatus.EXHAUSTED
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
    ) -> OutboundNotificationJob | None:
        job = self.get_by_public_id(db, team_id=team_id, public_id=public_id, for_update=True)
        if not self._owns_running_lease(job, lease_token):
            return None
        job.status = OutboundNotificationJobStatus.FAILED
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
    ) -> list[OutboundNotificationJobRecoveryCandidate]:
        resolved_now = now or business_now()
        attempt_limit = max(1, max_attempts)
        expired_running = and_(
            OutboundNotificationJob.status == OutboundNotificationJobStatus.RUNNING,
            or_(
                OutboundNotificationJob.lease_expires_at.is_(None),
                OutboundNotificationJob.lease_expires_at <= resolved_now,
            ),
        )
        due_failed = and_(
            OutboundNotificationJob.status == OutboundNotificationJobStatus.FAILED,
            or_(
                OutboundNotificationJob.next_attempt_at.is_(None),
                OutboundNotificationJob.next_attempt_at <= resolved_now,
            ),
        )
        claimable = and_(
            OutboundNotificationJob.attempt_count < attempt_limit,
            or_(
                OutboundNotificationJob.status == OutboundNotificationJobStatus.QUEUED,
                expired_running,
                due_failed,
            ),
        )
        needs_terminalization = and_(
            OutboundNotificationJob.attempt_count >= attempt_limit,
            or_(
                OutboundNotificationJob.status == OutboundNotificationJobStatus.QUEUED,
                OutboundNotificationJob.status == OutboundNotificationJobStatus.FAILED,
                expired_running,
            ),
        )
        rows = (
            db.query(
                OutboundNotificationJob.team_id,
                OutboundNotificationJob.public_id,
            )
            .filter(or_(claimable, needs_terminalization))
            .order_by(OutboundNotificationJob.created_time.asc(), OutboundNotificationJob.id.asc())
            .limit(max(1, limit))
            .all()
        )
        return [
            OutboundNotificationJobRecoveryCandidate(
                team_id=int(row.team_id),
                job_public_id=str(row.public_id),
            )
            for row in rows
        ]

    @staticmethod
    def _owns_running_lease(job: OutboundNotificationJob | None, lease_token: str) -> bool:
        return bool(
            job is not None
            and job.status == OutboundNotificationJobStatus.RUNNING
            and job.lease_token
            and job.lease_token == lease_token
        )


outbound_notification_job_crud = OutboundNotificationJobCRUD()
