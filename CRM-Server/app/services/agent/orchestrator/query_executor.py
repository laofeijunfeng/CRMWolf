"""Adapter from Root query execution input to the stateless CRM Query Agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from app.services.agent.query import CRMQueryAgentRequest, CRMQueryAgentResult
from app.services.agent.tools.base import AgentToolContext

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.agent.orchestrator.contracts import QueryExecutionInput, RootRuntimeContext
    from app.services.agent.query import CRMQueryAgentModelConfig


class CRMQueryAgentRunner(Protocol):
    async def run(
        self,
        request: CRMQueryAgentRequest,
        tool_context: AgentToolContext,
        model_config: CRMQueryAgentModelConfig,
    ) -> CRMQueryAgentResult: ...


class QueryExecutionConfigurationError(RuntimeError):
    """A required run-scoped dependency is absent at the Root seam."""


class CRMQueryAgentExecutor:
    """Translate one policy-filtered Root request into the existing Query Agent contract."""

    def __init__(self, *, query_agent: CRMQueryAgentRunner) -> None:
        self._query_agent = query_agent

    async def execute(
        self,
        request: QueryExecutionInput,
        *,
        runtime: RootRuntimeContext,
    ) -> CRMQueryAgentResult:
        if runtime.db is None:
            raise QueryExecutionConfigurationError("Query execution requires a database session")
        if not runtime.authorization:
            raise QueryExecutionConfigurationError("Query execution requires authorization")
        if runtime.query_model_config is None:
            raise QueryExecutionConfigurationError("Query execution requires model config")

        entity_refs = []
        if request.selected_entity is not None:
            entity_refs.append(request.selected_entity)
        if request.result_set is not None and request.selected_entity is None:
            known = {(ref.resource, ref.public_id) for ref in entity_refs}
            entity_refs.extend(
                ref for ref in request.result_set.ordered_entity_refs if (ref.resource, ref.public_id) not in known
            )

        return await self._query_agent.run(
            CRMQueryAgentRequest(
                user_message=request.text,
                previous_query=request.previous_query,
                entity_refs=entity_refs,
            ),
            AgentToolContext(
                db=cast("Session", runtime.db),
                team_id=request.principal.team_id,
                user_id=request.principal.user_id,
                session_id=request.principal.session_id,
                authorization=runtime.authorization,
                permission_codes=frozenset(request.principal.permission_codes),
                deadline_at=runtime.deadline_at,
            ),
            runtime.query_model_config,
        )
