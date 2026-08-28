"""Adapter from Root query execution input to the stateless CRM Query Agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from app.services.agent.query import (
    CRMQueryAgentRequest,
    CRMQueryAgentResponse,
    CRMQueryAgentResult,
    CRMQueryAgentTrace,
)
from app.services.agent.query.identity import (
    CustomerBinding,
    CustomerIdentityBindingError,
    CustomerQueryIdentityBinder,
)
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


class QueryIdentityResolutionUnavailableError(RuntimeError):
    """The authoritative customer identity seam could not complete."""


class CRMQueryAgentExecutor:
    """Translate one policy-filtered Root request into the existing Query Agent contract."""

    def __init__(
        self,
        *,
        query_agent: CRMQueryAgentRunner,
        identity_binder: CustomerQueryIdentityBinder | None = None,
    ) -> None:
        self._query_agent = query_agent
        self._identity_binder = identity_binder or CustomerQueryIdentityBinder()

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

        tool_context = AgentToolContext(
            db=cast("Session", runtime.db),
            team_id=request.principal.team_id,
            user_id=request.principal.user_id,
            session_id=request.principal.session_id,
            authorization=runtime.authorization,
            permission_codes=frozenset(request.principal.permission_codes),
            deadline_at=runtime.deadline_at,
        )

        entity_refs = []
        if request.selected_entity is not None:
            entity_refs.append(request.selected_entity)
        if request.result_set is not None and request.selected_entity is None:
            known = {(ref.resource, ref.public_id) for ref in entity_refs}
            entity_refs.extend(
                ref for ref in request.result_set.ordered_entity_refs if (ref.resource, ref.public_id) not in known
            )

        identity_intent = self._identity_binder.classify(request.text)
        allowed_tool_names: list[str] | None = None
        if identity_intent is not None and not entity_refs:
            try:
                binding = self._identity_binder.bind(identity_intent, tool_context)
            except CustomerIdentityBindingError as exc:
                raise QueryIdentityResolutionUnavailableError(
                    "Customer identity resolution is unavailable"
                ) from exc
            if binding.status != "BOUND":
                return self._identity_clarification(binding, runtime.query_model_config.model)
            entity_refs = [binding.entity_ref] if binding.entity_ref is not None else []
            allowed_tool_names = [identity_intent.tool_name]

        result = await self._query_agent.run(
            CRMQueryAgentRequest(
                user_message=request.text,
                previous_query=request.previous_query,
                entity_refs=entity_refs,
                allowed_tool_names=allowed_tool_names,
            ),
            tool_context,
            runtime.query_model_config,
        )
        if entity_refs:
            result = result.model_copy(update={"authoritative_entity_refs": entity_refs})
        return result

    @staticmethod
    def _identity_clarification(binding: CustomerBinding, model: str) -> CRMQueryAgentResult:
        if binding.status == "AMBIGUOUS":
            names = "、".join(ref.display_name for ref in binding.candidates[:5])
            question = f"请确认你要查询哪家客户\uFF1A{names}。"
        else:
            question = f"未找到与“{binding.query_text or '该客户'}”匹配的客户，请补充完整名称或客户简称。"  # noqa: RUF001
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="CLARIFICATION_REQUIRED",
                clarification_question=question,
            ),
            trace=CRMQueryAgentTrace(
                model=model,
                tool_names=[],
                tool_calls=[],
                tool_call_count=0,
                total_entity_count=0,
                elapsed_ms=0,
                stop_reason="CLARIFICATION_REQUIRED",
            ),
        )
