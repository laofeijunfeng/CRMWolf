"""Persistence interface for confirmed Agent application-step execution."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.models.agent_confirmed_application_step import (
    AgentConfirmedApplicationStep,
    AgentConfirmedApplicationStepStatus,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.agent.types import JSONDict


class AgentConfirmedApplicationStepCRUD:
    def get_by_step_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        step_id: str,
        for_update: bool = False,
    ) -> AgentConfirmedApplicationStep | None:
        query = db.query(AgentConfirmedApplicationStep).filter(
            AgentConfirmedApplicationStep.team_id == team_id,
            AgentConfirmedApplicationStep.user_id == user_id,
            AgentConfirmedApplicationStep.step_id == step_id,
        )
        if for_update:
            query = query.populate_existing().with_for_update()
        return query.one_or_none()

    def get_by_task_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        task_id: int,
        for_update: bool = False,
    ) -> AgentConfirmedApplicationStep | None:
        query = db.query(AgentConfirmedApplicationStep).filter(
            AgentConfirmedApplicationStep.team_id == team_id,
            AgentConfirmedApplicationStep.user_id == user_id,
            AgentConfirmedApplicationStep.task_id == task_id,
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
        task_id: int,
        step_id: str,
        step_type: str,
        request_json: JSONDict,
    ) -> AgentConfirmedApplicationStep:
        existing = self.get_by_step_id(db, team_id=team_id, user_id=user_id, step_id=step_id)
        if existing is not None:
            return existing
        candidate = AgentConfirmedApplicationStep(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            step_id=step_id,
            step_type=step_type,
            request_json=request_json,
            status=AgentConfirmedApplicationStepStatus.PENDING,
            attempt_count=0,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            existing = self.get_by_step_id(db, team_id=team_id, user_id=user_id, step_id=step_id)
            if existing is None:
                existing = self.get_by_task_id(
                    db,
                    team_id=team_id,
                    user_id=user_id,
                    task_id=task_id,
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
        lease_token: str | None = None,
        lease_seconds: int = 120,
    ) -> AgentConfirmedApplicationStep | None:
        now = business_now()
        record = self.get_by_step_id(
            db,
            team_id=team_id,
            user_id=user_id,
            step_id=step_id,
            for_update=True,
        )
        if record is None or record.status == AgentConfirmedApplicationStepStatus.COMPLETED:
            return None
        if (
            record.status == AgentConfirmedApplicationStepStatus.RUNNING
            and record.lease_expires_at is not None
            and record.lease_expires_at > now
        ):
            return None
        record.status = AgentConfirmedApplicationStepStatus.RUNNING
        record.attempt_count = int(record.attempt_count or 0) + 1
        record.lease_token = lease_token or uuid.uuid4().hex
        record.lease_expires_at = now + timedelta(seconds=max(1, lease_seconds))
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
    ) -> AgentConfirmedApplicationStep | None:
        record = self.get_by_step_id(
            db,
            team_id=team_id,
            user_id=user_id,
            step_id=step_id,
            for_update=True,
        )
        if (
            record is None
            or record.status != AgentConfirmedApplicationStepStatus.RUNNING
            or record.lease_token != lease_token
        ):
            return None
        record.status = AgentConfirmedApplicationStepStatus.COMPLETED
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
    ) -> AgentConfirmedApplicationStep | None:
        record = self.get_by_step_id(
            db,
            team_id=team_id,
            user_id=user_id,
            step_id=step_id,
            for_update=True,
        )
        if (
            record is None
            or record.status != AgentConfirmedApplicationStepStatus.RUNNING
            or record.lease_token != lease_token
        ):
            return None
        record.status = AgentConfirmedApplicationStepStatus.FAILED
        record.error_message = error_message[:4000]
        record.lease_token = None
        record.lease_expires_at = None
        db.add(record)
        db.commit()
        db.refresh(record)
        return record


agent_confirmed_application_step_crud = AgentConfirmedApplicationStepCRUD()
