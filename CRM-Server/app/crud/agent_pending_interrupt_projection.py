"""Persistence interface for PendingTask interrupt projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.models.agent_pending_interrupt_projection import (
    AgentPendingInterruptDeliveryStatus,
    AgentPendingInterruptProjection,
    AgentPendingInterruptProjectionStatus,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.services.agent.types import JSONDict


class AgentPendingInterruptProjectionCRUD:
    def get_by_key(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        projection_key: str,
        for_update: bool = False,
    ) -> AgentPendingInterruptProjection | None:
        query = db.query(AgentPendingInterruptProjection).filter(
            AgentPendingInterruptProjection.team_id == team_id,
            AgentPendingInterruptProjection.user_id == user_id,
            AgentPendingInterruptProjection.projection_key == projection_key,
        )
        if for_update:
            query = query.populate_existing().with_for_update()
        return query.one_or_none()

    def ensure(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        task_id: int | None,
        projection_key: str,
        continuation_json: JSONDict,
        interrupt_json: JSONDict,
        commit: bool = True,
    ) -> AgentPendingInterruptProjection:
        existing = self.get_by_key(
            db,
            team_id=team_id,
            user_id=user_id,
            projection_key=projection_key,
        )
        if existing is not None:
            return existing
        candidate = AgentPendingInterruptProjection(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            projection_key=projection_key,
            continuation_json=continuation_json,
            interrupt_json=interrupt_json,
            status=AgentPendingInterruptProjectionStatus.PENDING,
            delivery_status=AgentPendingInterruptDeliveryStatus.PENDING,
            attempt_count=0,
            delivery_attempt_count=0,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self.get_by_key(
                db,
                team_id=team_id,
                user_id=user_id,
                projection_key=projection_key,
            )
            if existing is None:
                raise
            return existing
        if commit:
            db.commit()
            db.refresh(candidate)
        return candidate

    def claim_projection(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        projection_key: str,
        lease_token: str,
        lease_expires_at: datetime,
        now: datetime | None = None,
        commit: bool = True,
    ) -> AgentPendingInterruptProjection | None:
        resolved_now = now or business_now()
        record = self.get_by_key(
            db,
            team_id=team_id,
            user_id=user_id,
            projection_key=projection_key,
            for_update=True,
        )
        if record is None or record.status == AgentPendingInterruptProjectionStatus.PROJECTED:
            return None
        if (
            record.status == AgentPendingInterruptProjectionStatus.PROJECTING
            and record.lease_expires_at is not None
            and record.lease_expires_at > resolved_now
        ):
            return None
        record.status = AgentPendingInterruptProjectionStatus.PROJECTING
        record.attempt_count = int(record.attempt_count or 0) + 1
        record.lease_token = lease_token
        record.lease_expires_at = lease_expires_at
        record.error_message = None
        db.add(record)
        self._finish(db, record, commit=commit)
        return record

    def mark_projected_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        projection_key: str,
        lease_token: str,
        result_json: JSONDict,
        commit: bool = True,
    ) -> AgentPendingInterruptProjection | None:
        record = self.get_by_key(
            db,
            team_id=team_id,
            user_id=user_id,
            projection_key=projection_key,
            for_update=True,
        )
        if not self._owns_projection_lease(record, lease_token):
            return None
        record.status = AgentPendingInterruptProjectionStatus.PROJECTED
        record.result_json = result_json
        record.error_message = None
        record.projected_at = business_now()
        record.lease_token = None
        record.lease_expires_at = None
        db.add(record)
        self._finish(db, record, commit=commit)
        return record

    def mark_projection_failed_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        projection_key: str,
        lease_token: str,
        error_message: str,
        commit: bool = True,
    ) -> AgentPendingInterruptProjection | None:
        record = self.get_by_key(
            db,
            team_id=team_id,
            user_id=user_id,
            projection_key=projection_key,
            for_update=True,
        )
        if not self._owns_projection_lease(record, lease_token):
            return None
        record.status = AgentPendingInterruptProjectionStatus.FAILED
        record.error_message = error_message[:4000]
        record.lease_token = None
        record.lease_expires_at = None
        db.add(record)
        self._finish(db, record, commit=commit)
        return record

    def claim_delivery(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        projection_key: str,
        lease_token: str,
        lease_expires_at: datetime,
        now: datetime | None = None,
        commit: bool = True,
    ) -> AgentPendingInterruptProjection | None:
        resolved_now = now or business_now()
        record = self.get_by_key(
            db,
            team_id=team_id,
            user_id=user_id,
            projection_key=projection_key,
            for_update=True,
        )
        if record is None or record.status != AgentPendingInterruptProjectionStatus.PROJECTED:
            return None
        if record.delivery_status in AgentPendingInterruptDeliveryStatus.TERMINAL:
            return None
        if (
            record.delivery_status == AgentPendingInterruptDeliveryStatus.DELIVERING
            and record.delivery_lease_expires_at is not None
            and record.delivery_lease_expires_at > resolved_now
        ):
            return None
        record.delivery_status = AgentPendingInterruptDeliveryStatus.DELIVERING
        record.delivery_attempt_count = int(record.delivery_attempt_count or 0) + 1
        record.delivery_lease_token = lease_token
        record.delivery_lease_expires_at = lease_expires_at
        record.delivery_reason_code = None
        record.delivery_error_message = None
        db.add(record)
        self._finish(db, record, commit=commit)
        return record

    def finish_delivery_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        projection_key: str,
        lease_token: str,
        status: str,
        error_message: str | None = None,
        reason_code: str | None = None,
        commit: bool = True,
    ) -> AgentPendingInterruptProjection | None:
        record = self.get_by_key(
            db,
            team_id=team_id,
            user_id=user_id,
            projection_key=projection_key,
            for_update=True,
        )
        if not self._owns_delivery_lease(record, lease_token):
            return None
        record.delivery_status = status
        record.delivery_reason_code = reason_code[:80] if reason_code else None
        record.delivery_error_message = error_message[:4000] if error_message else None
        record.delivered_at = business_now() if status in AgentPendingInterruptDeliveryStatus.TERMINAL else None
        record.delivery_lease_token = None
        record.delivery_lease_expires_at = None
        db.add(record)
        self._finish(db, record, commit=commit)
        return record

    @staticmethod
    def _finish(db: Session, record: AgentPendingInterruptProjection, *, commit: bool) -> None:
        if commit:
            db.commit()
            db.refresh(record)
        else:
            db.flush()

    @staticmethod
    def _owns_projection_lease(record: AgentPendingInterruptProjection | None, token: str) -> bool:
        return bool(
            record is not None
            and record.status == AgentPendingInterruptProjectionStatus.PROJECTING
            and record.lease_token == token
        )

    @staticmethod
    def _owns_delivery_lease(record: AgentPendingInterruptProjection | None, token: str) -> bool:
        return bool(
            record is not None
            and record.delivery_status == AgentPendingInterruptDeliveryStatus.DELIVERING
            and record.delivery_lease_token == token
        )


agent_pending_interrupt_projection_crud = AgentPendingInterruptProjectionCRUD()
