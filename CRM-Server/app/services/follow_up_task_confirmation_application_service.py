"""Apply resolved confirmation cases through the gated transition executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.crud.sales_commitment import follow_up_task_confirmation_case_crud, follow_up_task_crud
from app.models.sales_commitment import (
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskConfirmationStatus,
)
from app.services.follow_up_task_confirmation_service import (
    FollowUpTaskConfirmationReplyDecision,
    follow_up_task_confirmation_service,
)
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_execution_service import (
    FollowUpTaskTransitionExecutionResult,
    FollowUpTaskTransitionExecutionService,
    FollowUpTaskTransitionExecutionStatus,
    follow_up_task_transition_execution_service,
)
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionAction,
    FollowUpTaskTransitionPlan,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.sales_commitment import FollowUpTask, FollowUpTaskConfirmationCase
    from app.services.follow_up_task_confirmation_service import FollowUpTaskConfirmationService


class FollowUpTaskCrudProtocol(Protocol):
    def get_by_id(self, db: Session, task_id: int, team_id: int | None = None) -> FollowUpTask | None: ...


class FollowUpTaskConfirmationCaseCrudProtocol(Protocol):
    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int | None = None,
    ) -> FollowUpTaskConfirmationCase | None: ...

    def mark_application_result(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        application_status: str,
        applied_by_id: str,
        application_skip_reason: str | None = None,
        application_result_json: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase: ...


class FollowUpTaskConfirmationApplicationStatus:
    APPLIED = "APPLIED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class FollowUpTaskConfirmationApplicationResult:
    status: str
    case_public_id: str | None
    task_public_id: str | None
    action: str | None
    skip_reason: str | None = None
    execution_results: tuple[FollowUpTaskTransitionExecutionResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "case_public_id": self.case_public_id,
            "task_public_id": self.task_public_id,
            "action": self.action,
            "skip_reason": self.skip_reason,
            "execution_results": [result.to_dict() for result in self.execution_results],
        }


class FollowUpTaskConfirmationApplicationService:
    """Turns explicit user confirmation replies into audited task transitions."""

    mutating_actions = frozenset(
        {
            FollowUpTaskConfirmationResolutionAction.COMPLETE,
            FollowUpTaskConfirmationResolutionAction.DELAY,
            FollowUpTaskConfirmationResolutionAction.CANCEL,
        }
    )

    def __init__(
        self,
        *,
        confirmation_case_crud: FollowUpTaskConfirmationCaseCrudProtocol = follow_up_task_confirmation_case_crud,
        task_crud: FollowUpTaskCrudProtocol = follow_up_task_crud,
        confirmation_service: FollowUpTaskConfirmationService = follow_up_task_confirmation_service,
        execution_service: FollowUpTaskTransitionExecutionService = follow_up_task_transition_execution_service,
    ) -> None:
        self.confirmation_case_crud = confirmation_case_crud
        self.task_crud = task_crud
        self.confirmation_service = confirmation_service
        self.execution_service = execution_service

    def resolve_reply_and_apply(
        self,
        db: Session,
        *,
        team_id: int,
        case_public_id: str,
        actor_id: str,
        reply_text: str,
        base_date: datetime | None = None,
        commit: bool = True,
    ) -> tuple[
        FollowUpTaskConfirmationCase | None,
        FollowUpTaskConfirmationReplyDecision,
        FollowUpTaskConfirmationApplicationResult,
    ]:
        existing_case = self.confirmation_case_crud.get_by_public_id(db, case_public_id, team_id=team_id)
        decision = self.confirmation_service.interpret_reply(reply_text, base_date=base_date)
        if existing_case is None:
            return (
                None,
                decision,
                self._skipped(None, None, decision.action, "CONFIRMATION_CASE_NOT_FOUND"),
            )
        if actor_id != existing_case.owner_id:
            return (
                existing_case,
                decision,
                self._skipped(existing_case.public_id, None, decision.action, "CONFIRMATION_ACTOR_NOT_OWNER"),
            )

        case, decision = self.confirmation_service.resolve_case_from_reply(
            db,
            team_id=team_id,
            case_public_id=case_public_id,
            actor_id=actor_id,
            reply_text=reply_text,
            base_date=base_date,
            commit=False,
        )
        application = self.apply_resolved_case(
            db,
            team_id=team_id,
            case_public_id=case_public_id,
            actor_id=actor_id,
            commit=False,
        )
        if commit and (case is not None or application.status == FollowUpTaskConfirmationApplicationStatus.APPLIED):
            db.commit()
        return case, decision, application

    def apply_resolved_case(
        self,
        db: Session,
        *,
        team_id: int,
        case_public_id: str,
        actor_id: str,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationApplicationResult:
        case = self.confirmation_case_crud.get_by_public_id(db, case_public_id, team_id=team_id)
        if case is None:
            return self._skipped(None, None, None, "CONFIRMATION_CASE_NOT_FOUND")
        if case.status != FollowUpTaskConfirmationStatus.RESOLVED:
            return self._skipped(case.public_id, None, case.resolved_action, "CONFIRMATION_CASE_NOT_RESOLVED")
        if actor_id != case.owner_id:
            return self._skipped(case.public_id, None, case.resolved_action, "CONFIRMATION_ACTOR_NOT_OWNER")
        if case.application_status is not None:
            return self._recorded_application_result(db, case, team_id=team_id)
        if case.resolved_action == FollowUpTaskConfirmationResolutionAction.KEEP_OPEN:
            result = self._skipped(case.public_id, None, case.resolved_action, "KEEP_OPEN_NO_MUTATION")
            return self._persist_application_result(db, case=case, result=result, actor_id=actor_id, commit=commit)
        if case.resolved_action not in self.mutating_actions:
            result = self._skipped(case.public_id, None, case.resolved_action, "CONFIRMATION_ACTION_NOT_MUTATING")
            return self._persist_application_result(db, case=case, result=result, actor_id=actor_id, commit=commit)

        task = self.task_crud.get_by_id(db, case.task_id, team_id=team_id)
        if task is None:
            result = self._skipped(case.public_id, None, case.resolved_action, "TASK_NOT_FOUND")
            return self._persist_application_result(db, case=case, result=result, actor_id=actor_id, commit=commit)

        plan = self._plan_from_case(case, task)
        execution_results = tuple(
            self.execution_service.execute_plan(
                db,
                team_id=team_id,
                plan=plan,
                actor_id=actor_id,
                expected_owner_id=case.owner_id,
                enabled=True,
                commit=False,
            )
        )
        applied = any(result.status == FollowUpTaskTransitionExecutionStatus.EXECUTED for result in execution_results)
        if not applied:
            skip_reason = execution_results[0].skip_reason if execution_results else "EXECUTION_SKIPPED"
            result = self._skipped(
                case.public_id,
                task.public_id,
                case.resolved_action,
                skip_reason or "EXECUTION_SKIPPED",
                execution_results=execution_results,
            )
            return self._persist_application_result(db, case=case, result=result, actor_id=actor_id, commit=commit)
        result = FollowUpTaskConfirmationApplicationResult(
            status=FollowUpTaskConfirmationApplicationStatus.APPLIED,
            case_public_id=case.public_id,
            task_public_id=task.public_id,
            action=case.resolved_action,
            execution_results=execution_results,
        )
        return self._persist_application_result(db, case=case, result=result, actor_id=actor_id, commit=commit)

    def _plan_from_case(
        self,
        case: FollowUpTaskConfirmationCase,
        task: FollowUpTask,
    ) -> FollowUpTaskTransitionPlan:
        proposed_due_at = case.resolved_due_at.isoformat() if case.resolved_due_at is not None else None
        decision = FollowUpTaskReconciliationDecision(
            decision=case.resolved_action,
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=1.0,
            needs_confirmation=False,
            proposed_due_at=proposed_due_at,
            evidence_terms=("user_confirmation",),
            state_mutation_requested=False,
        )
        action = FollowUpTaskTransitionAction(
            action=case.resolved_action,
            task_public_id=task.public_id,
            confidence=1.0,
            executable=True,
            requires_confirmation=False,
            proposed_due_at=proposed_due_at,
            reason="USER_CONFIRMATION_RESOLVED",
            evidence_terms=("user_confirmation",),
            source_activity_public_id=case.source_public_id,
        )
        return FollowUpTaskTransitionPlan(
            decision=decision,
            actions=(action,),
            plan_source="confirmation_case_reply",
            safety_failures=(),
            state_mutation_requested=False,
        )

    def _skipped(
        self,
        case_public_id: str | None,
        task_public_id: str | None,
        action: str | None,
        reason: str,
        *,
        execution_results: tuple[FollowUpTaskTransitionExecutionResult, ...] = (),
    ) -> FollowUpTaskConfirmationApplicationResult:
        return FollowUpTaskConfirmationApplicationResult(
            status=FollowUpTaskConfirmationApplicationStatus.SKIPPED,
            case_public_id=case_public_id,
            task_public_id=task_public_id,
            action=action,
            skip_reason=reason,
            execution_results=execution_results,
        )

    def _persist_application_result(
        self,
        db: Session,
        *,
        case: FollowUpTaskConfirmationCase,
        result: FollowUpTaskConfirmationApplicationResult,
        actor_id: str,
        commit: bool,
    ) -> FollowUpTaskConfirmationApplicationResult:
        self.confirmation_case_crud.mark_application_result(
            db,
            case,
            application_status=result.status,
            application_skip_reason=result.skip_reason,
            application_result_json=result.to_dict(),
            applied_by_id=actor_id,
            commit=False,
        )
        if commit:
            db.commit()
            db.refresh(case)
        return result

    def _recorded_application_result(
        self,
        db: Session,
        case: FollowUpTaskConfirmationCase,
        *,
        team_id: int,
    ) -> FollowUpTaskConfirmationApplicationResult:
        task = self.task_crud.get_by_id(db, case.task_id, team_id=team_id)
        return FollowUpTaskConfirmationApplicationResult(
            status=case.application_status,
            case_public_id=case.public_id,
            task_public_id=task.public_id if task is not None else None,
            action=case.resolved_action,
            skip_reason=case.application_skip_reason,
        )


follow_up_task_confirmation_application_service = FollowUpTaskConfirmationApplicationService()
