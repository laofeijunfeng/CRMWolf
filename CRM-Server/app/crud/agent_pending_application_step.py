"""Persistence interface for hidden PendingTask application-step execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.models.agent_pending_application_step import (
    AgentPendingApplicationStep,
    AgentPendingApplicationStepStatus,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.services.agent.types import JSONDict


class AgentPendingApplicationStepCRUD:
    def get_by_step_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        step_id: str,
        for_update: bool = False,
    ) -> AgentPendingApplicationStep | None:
        query = db.query(AgentPendingApplicationStep).filter(
            AgentPendingApplicationStep.team_id == team_id,
            AgentPendingApplicationStep.user_id == user_id,
            AgentPendingApplicationStep.step_id == step_id,
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
        step_id: str,
        step_type: str,
        continuation_json: JSONDict,
        request_json: JSONDict,
    ) -> AgentPendingApplicationStep:
        existing = self.get_by_step_id(
            db,
            team_id=team_id,
            user_id=user_id,
            step_id=step_id,
        )
        if existing is not None:
            return existing
        candidate = AgentPendingApplicationStep(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            continuation_json=continuation_json,
            request_json=request_json,
            status=AgentPendingApplicationStepStatus.PENDING,
            attempt_count=0,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self.get_by_step_id(
                db,
                team_id=team_id,
                user_id=user_id,
                step_id=step_id,
            )
            if existing is None:
                raise
            return existing
        db.commit()
        db.refresh(candidate)
        return candidate

    def claim(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        step_id: str,
        lease_token: str,
        lease_expires_at: datetime,
        now: datetime | None = None,
    ) -> AgentPendingApplicationStep | None:
        resolved_now = now or business_now()
        record = self.get_by_step_id(
            db,
            team_id=team_id,
            user_id=user_id,
            step_id=step_id,
            for_update=True,
        )
        if record is None or record.status == AgentPendingApplicationStepStatus.COMPLETED:
            return None
        if (
            record.status == AgentPendingApplicationStepStatus.RUNNING
            and record.lease_expires_at is not None
            and record.lease_expires_at > resolved_now
        ):
            return None
        record.status = AgentPendingApplicationStepStatus.RUNNING
        record.attempt_count = int(record.attempt_count or 0) + 1
        record.lease_token = lease_token
        record.lease_expires_at = lease_expires_at
        record.error_message = None
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def complete_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        step_id: str,
        lease_token: str,
        result_json: JSONDict,
    ) -> AgentPendingApplicationStep | None:
        record = self.get_by_step_id(
            db,
            team_id=team_id,
            user_id=user_id,
            step_id=step_id,
            for_update=True,
        )
        if record is None or record.status != AgentPendingApplicationStepStatus.RUNNING:
            return None
        if record.lease_token != lease_token:
            return None
        record.status = AgentPendingApplicationStepStatus.COMPLETED
        record.result_json = result_json
        record.error_message = None
        record.completed_at = business_now()
        record.lease_token = None
        record.lease_expires_at = None
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def fail_if_lease_owner(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        step_id: str,
        lease_token: str,
        error_message: str,
    ) -> AgentPendingApplicationStep | None:
        record = self.get_by_step_id(
            db,
            team_id=team_id,
            user_id=user_id,
            step_id=step_id,
            for_update=True,
        )
        if record is None or record.status != AgentPendingApplicationStepStatus.RUNNING:
            return None
        if record.lease_token != lease_token:
            return None
        record.status = AgentPendingApplicationStepStatus.FAILED
        record.error_message = error_message
        record.lease_token = None
        record.lease_expires_at = None
        db.add(record)
        db.commit()
        db.refresh(record)
        return record


agent_pending_application_step_crud = AgentPendingApplicationStepCRUD()
