"""Authoritative persistence-backed context for the Root Orchestrator."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent.orchestrator.contracts import (
    ResultSetContext,
    RootContextSnapshot,
)
from app.services.agent.orchestrator.errors import RootContextUnavailableError
from app.services.agent.query.result_sets import (
    AgentQueryResultSetRepository,
    ResultSetError,
)
from app.services.agent.ui.actions import AgentUIActionRepository

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
    ) -> None:
        self._result_set_repository = result_set_repository or AgentQueryResultSetRepository()
        self._action_repository = action_repository or AgentUIActionRepository()

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
        except (ResultSetError, SQLAlchemyError, ValidationError, TypeError, ValueError) as exc:
            raise RootContextUnavailableError("Canonical query context could not be loaded safely") from exc

        active_workflow = continuations[0].workflow_ref if continuations else None
        resumable_workflows = [continuation.workflow_ref for continuation in continuations]
        if result_set is None:
            return RootContextSnapshot(
                active_workflow=active_workflow,
                resumable_workflows=resumable_workflows,
            )
        return RootContextSnapshot(
            previous_query=result_set.query,
            result_set=ResultSetContext(
                result_set_id=result_set.public_id,
                ordered_entity_refs=result_set.ordered_entity_refs,
            ),
            active_workflow=active_workflow,
            resumable_workflows=resumable_workflows,
        )
