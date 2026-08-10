"""Gated executor for follow-up task transition plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from app.crud.sales_commitment import follow_up_task_crud, follow_up_task_event_crud
from app.models.sales_commitment import FollowUpTaskEventType, FollowUpTaskStatus
from app.schemas.sales_commitment import FollowUpTaskInternalUpdate
from app.services.customer_vector_document_service import customer_vector_document_service
from app.services.follow_up_task_confirmation_cleanup_service import (
    FollowUpTaskConfirmationCancelReason,
    follow_up_task_confirmation_cleanup_service,
)
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionAction,
    FollowUpTaskTransitionActionType,
    FollowUpTaskTransitionPlan,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent


class FollowUpTaskCrudProtocol(Protocol):
    def get_by_id(self, db: Session, task_id: int, team_id: int | None = None) -> FollowUpTask | None: ...

    def get_by_public_id(self, db: Session, public_id: str, team_id: int | None = None) -> FollowUpTask | None: ...

    def complete(self, db: Session, db_obj: FollowUpTask, *, commit: bool = True) -> FollowUpTask: ...

    def cancel(self, db: Session, db_obj: FollowUpTask, *, commit: bool = True) -> FollowUpTask: ...

    def reopen(self, db: Session, db_obj: FollowUpTask, *, commit: bool = True) -> FollowUpTask: ...

    def update(
        self,
        db: Session,
        db_obj: FollowUpTask,
        obj_in: FollowUpTaskInternalUpdate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTask: ...


class FollowUpTaskEventCrudProtocol(Protocol):
    def get_by_public_id(self, db: Session, public_id: str, team_id: int | None = None) -> FollowUpTaskEvent | None: ...

    def list_by_task(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FollowUpTaskEvent], int]: ...

    def record_status_change(
        self,
        db: Session,
        *,
        task: FollowUpTask,
        event_type: str,
        actor_id: str | None,
        previous_status: str | None,
        payload_json: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> FollowUpTaskEvent: ...


class FollowUpTaskConfirmationCleanupProtocol(Protocol):
    def cancel_pending_cases_for_task(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
        actor_id: str | None = None,
        reason: str,
        commit: bool = True,
    ) -> object: ...


class CustomerVectorDocumentServiceProtocol(Protocol):
    def upsert_follow_up_task(self, db: Session, task: FollowUpTask, *, commit: bool = True) -> object: ...


class FollowUpTaskTransitionExecutionStatus:
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    DISABLED = "DISABLED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class FollowUpTaskTransitionExecutionResult:
    """Execution outcome for a single transition action."""

    status: str
    action: str
    task_public_id: str | None
    previous_status: str | None = None
    new_status: str | None = None
    skip_reason: str | None = None
    event_type: str | None = None
    payload_json: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "task_public_id": self.task_public_id,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "skip_reason": self.skip_reason,
            "event_type": self.event_type,
            "payload_json": self.payload_json,
        }


class FollowUpTaskTransitionExecutionService:
    """Executes already-approved transition plans behind an explicit gate."""

    def __init__(
        self,
        *,
        task_crud: FollowUpTaskCrudProtocol = follow_up_task_crud,
        event_crud: FollowUpTaskEventCrudProtocol = follow_up_task_event_crud,
        confirmation_cleanup_service: FollowUpTaskConfirmationCleanupProtocol = (
            follow_up_task_confirmation_cleanup_service
        ),
        vector_document_service: CustomerVectorDocumentServiceProtocol = customer_vector_document_service,
    ) -> None:
        self.task_crud = task_crud
        self.event_crud = event_crud
        self.confirmation_cleanup_service = confirmation_cleanup_service
        self.vector_document_service = vector_document_service

    def execute_plan(
        self,
        db: Session,
        *,
        team_id: int,
        plan: FollowUpTaskTransitionPlan,
        actor_id: str | None,
        expected_owner_id: str | None = None,
        enabled: bool = False,
        commit: bool = True,
    ) -> list[FollowUpTaskTransitionExecutionResult]:
        results = [
            self.execute_action(
                db,
                team_id=team_id,
                action=action,
                plan=plan,
                actor_id=actor_id,
                expected_owner_id=expected_owner_id,
                enabled=enabled,
                commit=False,
            )
            for action in plan.actions
        ]
        has_executed_action = any(result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED for result in results)
        if enabled and commit and has_executed_action:
            db.commit()
        return results

    def execute_action(
        self,
        db: Session,
        *,
        team_id: int,
        action: FollowUpTaskTransitionAction,
        plan: FollowUpTaskTransitionPlan,
        actor_id: str | None,
        expected_owner_id: str | None = None,
        enabled: bool = False,
        commit: bool = True,
    ) -> FollowUpTaskTransitionExecutionResult:
        if not enabled:
            return self._skipped(
                action,
                status=FollowUpTaskTransitionExecutionStatus.DISABLED,
                reason="EXECUTOR_DISABLED",
            )
        if plan.state_mutation_requested:
            return self._skipped(action, reason="PLAN_STATE_MUTATION_REQUESTED")
        if plan.safety_failures:
            return self._skipped(action, reason="PLAN_SAFETY_FAILURES")
        if not action.executable:
            return self._skipped(action, reason="ACTION_NOT_EXECUTABLE")
        if action.requires_confirmation:
            return self._skipped(action, reason="ACTION_REQUIRES_CONFIRMATION")
        if action.action not in {
            FollowUpTaskTransitionActionType.COMPLETE,
            FollowUpTaskTransitionActionType.DELAY,
            FollowUpTaskTransitionActionType.CANCEL,
        }:
            return self._skipped(action, reason="ACTION_NOT_MUTATING")
        if not action.task_public_id:
            return self._skipped(action, reason="TASK_PUBLIC_ID_MISSING")

        task = self.task_crud.get_by_public_id(db, action.task_public_id, team_id=team_id)
        if task is None:
            return self._skipped(action, reason="TASK_NOT_FOUND")
        expected_owner = expected_owner_id or actor_id
        if expected_owner and task.owner_id != expected_owner:
            return self._skipped(action, reason="TASK_OWNER_MISMATCH")
        if task.status != FollowUpTaskStatus.OPEN:
            return self._skipped(action, reason="TASK_NOT_OPEN", previous_status=task.status)

        previous_status = task.status
        payload = self._event_payload(action, plan, task)
        if action.action == FollowUpTaskTransitionActionType.COMPLETE:
            self.task_crud.complete(db, task, commit=False)
            event_type = FollowUpTaskEventType.COMPLETED
        elif action.action == FollowUpTaskTransitionActionType.CANCEL:
            self.task_crud.cancel(db, task, commit=False)
            event_type = FollowUpTaskEventType.CANCELLED
        else:
            due_at = self._parse_due_at(action.proposed_due_at)
            if due_at is None:
                return self._skipped(action, reason="DELAY_DUE_AT_INVALID", previous_status=previous_status)
            self.task_crud.update(
                db,
                task,
                FollowUpTaskInternalUpdate(
                    due_at=due_at,
                    due_at_text=action.proposed_due_at,
                    evidence_json={
                        **(task.evidence_json or {}),
                        "transition_plan": payload,
                    },
                ),
                commit=False,
            )
            event_type = FollowUpTaskEventType.UPDATED

        self.event_crud.record_status_change(
            db,
            task=task,
            event_type=event_type,
            actor_id=actor_id,
            previous_status=previous_status,
            payload_json=payload,
            commit=False,
        )
        if action.action in {
            FollowUpTaskTransitionActionType.COMPLETE,
            FollowUpTaskTransitionActionType.CANCEL,
        }:
            self.confirmation_cleanup_service.cancel_pending_cases_for_task(
                db,
                team_id=team_id,
                task_id=task.id,
                actor_id=actor_id,
                reason=(
                    FollowUpTaskConfirmationCancelReason.TASK_COMPLETED
                    if action.action == FollowUpTaskTransitionActionType.COMPLETE
                    else FollowUpTaskConfirmationCancelReason.TASK_CANCELLED
                ),
                commit=False,
            )
        self.vector_document_service.upsert_follow_up_task(db, task, commit=False)
        if commit:
            db.commit()
            db.refresh(task)

        return FollowUpTaskTransitionExecutionResult(
            status=FollowUpTaskTransitionExecutionStatus.EXECUTED,
            action=action.action,
            task_public_id=task.public_id,
            previous_status=previous_status,
            new_status=task.status,
            event_type=event_type,
            payload_json=payload,
        )

    def rollback_event(
        self,
        db: Session,
        *,
        team_id: int,
        event_public_id: str,
        actor_id: str | None,
        expected_owner_id: str | None = None,
        commit: bool = True,
    ) -> FollowUpTaskTransitionExecutionResult:
        event = self.event_crud.get_by_public_id(db, event_public_id, team_id=team_id)
        if event is None:
            return self._rollback_skipped("EVENT_NOT_FOUND")

        payload = event.payload_json or {}
        rollback = payload.get("rollback")
        if payload.get("reason") != "RECONCILIATION_TRANSITION_PLAN_EXECUTED" or not isinstance(rollback, dict):
            return self._rollback_skipped("EVENT_NOT_ROLLBACKABLE")
        if payload.get("execution_kind") != "automatic":
            return self._rollback_skipped("EVENT_NOT_AUTOMATIC_TRANSITION")

        task = self.task_crud.get_by_id(db, event.task_id, team_id=team_id)
        if task is None:
            return self._rollback_skipped("TASK_NOT_FOUND")
        expected_owner = expected_owner_id or actor_id
        if expected_owner and task.owner_id != expected_owner:
            return self._rollback_skipped("TASK_OWNER_MISMATCH", task_public_id=task.public_id)
        if self._has_rollback_event(db, team_id=team_id, task_id=task.id, event_public_id=event_public_id):
            return self._rollback_skipped("EVENT_ALREADY_ROLLED_BACK", task_public_id=task.public_id)

        previous_status = task.status
        rollback_type = rollback.get("type")
        if rollback_type == "REOPEN":
            self.task_crud.reopen(db, task, commit=False)
            event_type = FollowUpTaskEventType.REOPENED
        elif rollback_type == "RESTORE_DUE_AT":
            due_at = self._parse_due_at(rollback.get("previous_due_at"))
            if due_at is None:
                return self._rollback_skipped("ROLLBACK_DUE_AT_INVALID", task_public_id=task.public_id)
            self.task_crud.update(
                db,
                task,
                FollowUpTaskInternalUpdate(
                    status=rollback.get("previous_status") or FollowUpTaskStatus.OPEN,
                    due_at=due_at,
                    due_at_text=rollback.get("previous_due_at_text"),
                    due_at_granularity=rollback.get("previous_due_at_granularity"),
                    due_at_timezone=rollback.get("previous_due_at_timezone"),
                ),
                commit=False,
            )
            event_type = FollowUpTaskEventType.UPDATED
        else:
            return self._rollback_skipped("ROLLBACK_TYPE_UNSUPPORTED", task_public_id=task.public_id)

        rollback_payload = {
            "reason": "RECONCILIATION_TRANSITION_ROLLBACK",
            "rolled_back_event_public_id": event_public_id,
            "rolled_back_action": payload.get("action"),
            "task_public_id": task.public_id,
            "previous_status": previous_status,
            "new_status": task.status,
            "restored_due_at": task.due_at.isoformat() if task.due_at else None,
            "restored_due_at_text": task.due_at_text,
        }
        self.event_crud.record_status_change(
            db,
            task=task,
            event_type=event_type,
            actor_id=actor_id,
            previous_status=previous_status,
            payload_json=rollback_payload,
            commit=False,
        )
        self.vector_document_service.upsert_follow_up_task(db, task, commit=False)
        if commit:
            db.commit()
            db.refresh(task)

        return FollowUpTaskTransitionExecutionResult(
            status=FollowUpTaskTransitionExecutionStatus.EXECUTED,
            action="ROLLBACK",
            task_public_id=task.public_id,
            previous_status=previous_status,
            new_status=task.status,
            event_type=event_type,
            payload_json=rollback_payload,
        )

    def _event_payload(
        self,
        action: FollowUpTaskTransitionAction,
        plan: FollowUpTaskTransitionPlan,
        task: FollowUpTask,
    ) -> dict[str, Any]:
        return {
            "reason": "RECONCILIATION_TRANSITION_PLAN_EXECUTED",
            "plan_source": plan.plan_source,
            "execution_kind": self._execution_kind(plan),
            "action": action.action,
            "task_public_id": action.task_public_id,
            "confidence": action.confidence,
            "evidence_terms": list(action.evidence_terms),
            "source_activity_public_id": action.source_activity_public_id,
            "proposed_due_at": action.proposed_due_at,
            "decision": plan.decision.decision,
            "rollback": self._rollback_snapshot(action, task),
        }

    def _execution_kind(self, plan: FollowUpTaskTransitionPlan) -> str:
        if plan.plan_source == "manual_ui":
            return "manual_ui"
        if plan.plan_source == "confirmation_case_reply":
            return "manual_confirmation"
        return "automatic"

    def _rollback_snapshot(
        self,
        action: FollowUpTaskTransitionAction,
        task: FollowUpTask,
    ) -> dict[str, Any]:
        snapshot = {
            "previous_status": task.status,
            "previous_due_at": task.due_at.isoformat() if task.due_at else None,
            "previous_due_at_text": task.due_at_text,
            "previous_due_at_granularity": task.due_at_granularity,
            "previous_due_at_timezone": task.due_at_timezone,
        }
        if action.action in {
            FollowUpTaskTransitionActionType.COMPLETE,
            FollowUpTaskTransitionActionType.CANCEL,
        }:
            return {"type": "REOPEN", **snapshot}
        return {"type": "RESTORE_DUE_AT", **snapshot}

    def _has_rollback_event(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
        event_public_id: str,
    ) -> bool:
        events, _ = self.event_crud.list_by_task(db, team_id=team_id, task_id=task_id, limit=500)
        return any(
            isinstance(event.payload_json, dict)
            and event.payload_json.get("reason") == "RECONCILIATION_TRANSITION_ROLLBACK"
            and event.payload_json.get("rolled_back_event_public_id") == event_public_id
            for event in events
        )

    def _skipped(
        self,
        action: FollowUpTaskTransitionAction,
        *,
        reason: str,
        status: str = FollowUpTaskTransitionExecutionStatus.SKIPPED,
        previous_status: str | None = None,
    ) -> FollowUpTaskTransitionExecutionResult:
        return FollowUpTaskTransitionExecutionResult(
            status=status,
            action=action.action,
            task_public_id=action.task_public_id,
            previous_status=previous_status,
            skip_reason=reason,
        )

    def _rollback_skipped(
        self,
        reason: str,
        *,
        task_public_id: str | None = None,
    ) -> FollowUpTaskTransitionExecutionResult:
        return FollowUpTaskTransitionExecutionResult(
            status=FollowUpTaskTransitionExecutionStatus.SKIPPED,
            action="ROLLBACK",
            task_public_id=task_public_id,
            skip_reason=reason,
        )

    def _parse_due_at(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


follow_up_task_transition_execution_service = FollowUpTaskTransitionExecutionService()
