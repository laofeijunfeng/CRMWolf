"""Authoritative persistence-backed context for the Root Orchestrator."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.crud.sales_commitment import follow_up_task_confirmation_case_crud
from app.services.agent.orchestrator.contracts import (
    PendingCaseContext,
    ResultSetContext,
    RootContextSnapshot,
)
from app.services.agent.orchestrator.errors import RootContextUnavailableError
from app.services.agent.query.result_sets import (
    AgentQueryResultSetRepository,
    ResultSetError,
)
from app.services.agent.ui.actions import AgentUIActionRepository
from app.services.customer_alias_service import CustomerAliasService, customer_alias_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.agent.orchestrator.contracts import (
        RootRuntimeContext,
        RootTurnInput,
    )



class DatabaseRootContextResolver:
    """Resolve canonical query and active Workflow context from persistence."""

    def __init__(
        self,
        *,
        result_set_repository: AgentQueryResultSetRepository | None = None,
        action_repository: AgentUIActionRepository | None = None,
        alias_service: CustomerAliasService | None = None,
    ) -> None:
        self._result_set_repository = result_set_repository or AgentQueryResultSetRepository()
        self._action_repository = action_repository or AgentUIActionRepository()
        self._alias_service = alias_service or customer_alias_service

    async def resolve(
        self,
        *,
        turn: RootTurnInput,
        runtime: RootRuntimeContext,
    ) -> RootContextSnapshot:
        if runtime.db is None:
            raise RootContextUnavailableError("Root context resolution requires a database session")

        now = runtime.metadata.get("now")
        effective_now = now if isinstance(now, datetime) else None

        try:
            db = cast("Session", runtime.db)
            result_set = self._result_set_repository.get_latest_active(
                db,
                team_id=turn.team_id,
                user_id=turn.user_id,
                session_id=turn.session_id,
                now=effective_now,
            )
            continuations = self._action_repository.list_active_workflow_continuations(
                db,
                team_id=turn.team_id,
                user_id=turn.user_id,
                session_id=turn.session_id,
                now=effective_now,
            )
            pending_case_rows = follow_up_task_confirmation_case_crud.list_pending_context_for_owner(
                db,
                team_id=turn.team_id,
                owner_id=str(turn.user_id),
                now=effective_now,
            )
        except (ResultSetError, SQLAlchemyError, ValidationError, TypeError, ValueError) as exc:
            raise RootContextUnavailableError("Canonical query context could not be loaded safely") from exc

        active_workflow = continuations[0].workflow_ref if continuations else None
        resumable_workflows = [continuation.workflow_ref for continuation in continuations]
        pending_cases = [
            PendingCaseContext(
                case_public_id=str(case.public_id),
                customer_name=str(customer_name),
                customer_aliases=[
                    alias
                    for alias in self._alias_service.list_aliases_for_customer(
                        db,
                        team_id=turn.team_id,
                        customer_id=int(customer_id),
                        account_name=str(customer_name),
                    )
                    if alias != str(customer_name)
                ][:20],
                task_title=str(task_title),
                task_description=(str(task_description) if task_description is not None else None),
                due_at_text=(str(due_at_text) if due_at_text is not None else None),
                question_text=str(case.question_text),
            )
            for case, customer_id, customer_name, task_title, task_description, due_at_text in pending_case_rows
        ]
        if result_set is None:
            return RootContextSnapshot(
                active_workflow=active_workflow,
                resumable_workflows=resumable_workflows,
                resumable_workflow_continuations=continuations,
                pending_cases=pending_cases,
            )
        return RootContextSnapshot(
            previous_query=result_set.query,
            result_set=ResultSetContext(
                result_set_id=result_set.public_id,
                ordered_entity_refs=result_set.ordered_entity_refs,
            ),
            active_workflow=active_workflow,
            resumable_workflows=resumable_workflows,
            resumable_workflow_continuations=continuations,
            pending_cases=pending_cases,
        )
