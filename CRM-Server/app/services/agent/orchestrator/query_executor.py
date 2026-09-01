"""Adapter from Root query execution input to the stateless CRM Query Agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from app.services.agent.query import (
    CRMFilter,
    CRMQueryAgentRequest,
    CRMQueryAgentResponse,
    CRMQueryAgentResult,
    CRMQueryAgentTrace,
)
from app.services.agent.query.identity import (
    CustomerBinding,
    CustomerIdentityBindingError,
    CustomerQueryIdentityBinder,
    CustomerQueryIntent,
)
from app.services.agent.query.semantic_intent import (
    CRMQuerySemanticIntent,
    LLMQuerySemanticIntentResolver,
    QuerySemanticIntentInvalidError,
    QuerySemanticIntentUnavailableError,
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


class QuerySemanticResolutionUnavailableError(RuntimeError):
    """The LLM semantic query boundary could not complete."""


class CRMQueryAgentExecutor:
    """Translate one policy-filtered Root request into the existing Query Agent contract."""

    def __init__(
        self,
        *,
        query_agent: CRMQueryAgentRunner,
        identity_binder: CustomerQueryIdentityBinder | None = None,
        semantic_intent_resolver: LLMQuerySemanticIntentResolver | None = None,
    ) -> None:
        self._query_agent = query_agent
        self._identity_binder = identity_binder or CustomerQueryIdentityBinder()
        self._semantic_intent_resolver = semantic_intent_resolver or LLMQuerySemanticIntentResolver()

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

        semantic_intent: CRMQuerySemanticIntent | None = request.semantic_intent
        # Entity context answers *which customer* is in scope, but it does
        # not answer *what the user wants to read* or *which time window*
        # applies. The Query seam must still resolve semantics whenever Root
        # did not provide its preflight result; otherwise a selected customer
        # could silently fall through to an unconstrained Query Agent call.
        if semantic_intent is None:
            try:
                semantic_intent = await self._semantic_intent_resolver.resolve(
                    request.text,
                    model_config=runtime.query_model_config,
                    runtime=runtime,
                )
            except (QuerySemanticIntentUnavailableError, QuerySemanticIntentInvalidError) as exc:
                raise QuerySemanticResolutionUnavailableError(
                    "Query semantic intent resolution is unavailable"
                ) from exc

        allowed_tool_names: list[str] | None = None
        authoritative_filters: list[CRMFilter] = []
        authoritative_scope: str | None = None
        if semantic_intent is not None and semantic_intent.scope == "unknown":
            return self._ambiguous_semantic_intent_clarification(
                runtime.query_model_config.model,
            )
        # A recognized work resource with an unsupported temporal meaning is
        # safer to explain specifically than to collapse into the generic
        # low-confidence message. No Query Agent call is allowed in either
        # case; this keeps date interpretation server-owned.
        if (
            semantic_intent is not None
            and semantic_intent.scope == "global_work"
            and not self._global_work_constraints(semantic_intent)[0]
        ):
            return self._unsupported_global_work_clarification(
                runtime.query_model_config.model,
            )
        if semantic_intent is not None and semantic_intent.confidence < 0.80:
            return self._ambiguous_semantic_intent_clarification(
                runtime.query_model_config.model,
            )
        if semantic_intent is not None and semantic_intent.scope == "customer_list":
            # A customer-list query is still a bounded read.  Do not let the
            # Query Agent broaden it into contacts, activities, or work just
            # because the user's wording contains a second question.
            allowed_tool_names = ["query_customers"]
        if semantic_intent is not None and semantic_intent.scope == "global_work":
            authoritative_scope = "mine"
            allowed_tool_names, authoritative_filters = self._global_work_constraints(semantic_intent)
            if not allowed_tool_names:
                return self._unsupported_global_work_clarification(
                    runtime.query_model_config.model,
                )

        if semantic_intent is not None and semantic_intent.scope == "customer_scoped":
            tool_name = self._customer_tool_name(semantic_intent)
            if not entity_refs:
                identity_intent = CustomerQueryIntent(
                    tool_name=tool_name,
                    customer_text=semantic_intent.customer_text or request.text,
                )
                try:
                    binding = self._identity_binder.bind(identity_intent, tool_context)
                except CustomerIdentityBindingError as exc:
                    raise QueryIdentityResolutionUnavailableError(
                        "Customer identity resolution is unavailable"
                    ) from exc
                if binding.status != "BOUND":
                    return self._identity_clarification(binding, runtime.query_model_config.model)
                entity_refs = [binding.entity_ref] if binding.entity_ref is not None else []
            # The selected entity only resolves identity. Resource and temporal
            # semantics still come from the LLM contract and are enforced here
            # for both text-bound and context-bound customers.
            allowed_tool_names = [tool_name]
            customer_filters = self._customer_work_constraints(semantic_intent)
            if customer_filters is None:
                return self._unsupported_customer_work_clarification(
                    runtime.query_model_config.model,
                    semantic_intent,
                )
            authoritative_filters.extend(customer_filters)

        result = await self._query_agent.run(
            CRMQueryAgentRequest(
                user_message=request.text,
                previous_query=request.previous_query,
                entity_refs=entity_refs,
                allowed_tool_names=allowed_tool_names,
                authoritative_filters=authoritative_filters,
                authoritative_scope=authoritative_scope,
            ),
            tool_context,
            runtime.query_model_config,
        )
        if entity_refs:
            result = result.model_copy(update={"authoritative_entity_refs": entity_refs})
        return result

    @staticmethod
    def _customer_tool_name(intent: CRMQuerySemanticIntent) -> str:
        mapping = {
            "follow_up_tasks": "query_follow_up_tasks",
            "completed_work": "query_completed_work",
            "customer_context": "get_customer_context",
            "customer_activities": "query_customer_activities",
            "customer_contacts": "query_customer_contacts",
            "deployment_info": "query_customer_deployment_infos",
        }
        return mapping[intent.resource or "customer_context"]

    @staticmethod
    def _customer_work_constraints(intent: CRMQuerySemanticIntent) -> list[CRMFilter] | None:
        """Turn customer-scoped work time into server-owned filters.

        Customer identity is bound separately, but the Query Agent must not be
        left to reinterpret the temporal part of a customer work question.
        ``None`` means the closed contract is too ambiguous to execute safely;
        an empty list is a valid unbounded customer task query.
        """

        if intent.resource == "follow_up_tasks":
            filters = [CRMFilter(field="status", operator="eq", value="open")]
            temporal = intent.temporal
            if temporal.kind == "custom":
                filters.append(
                    CRMFilter(
                        field="tracking_time",
                        operator="between",
                        value=[temporal.start_at, temporal.end_at],
                    )
                )
            elif temporal.kind in {"today", "tomorrow", "this_week", "next_week", "overdue"}:
                filters.append(CRMFilter(field="due_window", operator="eq", value=temporal.kind))
            elif temporal.kind not in {"unspecified"}:
                return None
            return filters

        if intent.resource == "completed_work":
            temporal = intent.temporal
            if temporal.kind == "custom":
                return [
                    CRMFilter(
                        field="occurred_at",
                        operator="between",
                        value=[temporal.start_at, temporal.end_at],
                    )
                ]
            if temporal.kind in {"today", "this_week", "last_week", "this_month"}:
                return [CRMFilter(field="window", operator="eq", value=temporal.kind)]
            # completed-work API has a this_week default. Do not let that
            # implementation default answer an underspecified question.
            if temporal.kind == "unspecified":
                return None
            return None

        return []

    @staticmethod
    def _global_work_constraints(intent: CRMQuerySemanticIntent) -> tuple[list[str], list[CRMFilter]]:
        temporal = intent.temporal
        if intent.resource == "follow_up_tasks":
            filters = [CRMFilter(field="status", operator="eq", value="open")]
            if temporal.kind == "custom":
                filters.append(
                    CRMFilter(
                        field="tracking_time",
                        operator="between",
                        value=[temporal.start_at, temporal.end_at],
                    )
                )
            elif temporal.kind in {"today", "tomorrow", "this_week", "next_week", "overdue"}:
                filters.append(CRMFilter(field="due_window", operator="eq", value=temporal.kind))
            else:
                return [], []
            return ["query_follow_up_tasks"], filters

        if intent.resource == "completed_work":
            if temporal.kind == "custom":
                return ["query_completed_work"], [
                    CRMFilter(
                        field="occurred_at",
                        operator="between",
                        value=[temporal.start_at, temporal.end_at],
                    )
                ]
            if temporal.kind in {"today", "this_week", "last_week", "this_month"}:
                return ["query_completed_work"], [
                    CRMFilter(field="window", operator="eq", value=temporal.kind),
                ]
        return [], []

    @staticmethod
    def _ambiguous_semantic_intent_clarification(model: str) -> CRMQueryAgentResult:
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="CLARIFICATION_REQUIRED",
                clarification_question=(
                    "我还不能确定你要查询哪类 CRM 信息，请补充客户、事项或时间范围。"
                ),
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

    @staticmethod
    def _unsupported_customer_work_clarification(
        model: str,
        intent: CRMQuerySemanticIntent,
    ) -> CRMQueryAgentResult:
        resource = "已完成工作" if intent.resource == "completed_work" else "待办"
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="CLARIFICATION_REQUIRED",
                clarification_question=(
                    f"我识别到你是在查询该客户的{resource}, 但暂时无法确定时间范围。"
                    "请补充具体日期、日期区间或明确的自然时间周期。"
                ),
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

    @staticmethod
    def _unsupported_global_work_clarification(model: str) -> CRMQueryAgentResult:
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="CLARIFICATION_REQUIRED",
                clarification_question=(
                    "我识别到你是在查询个人工作安排, 但暂时无法确定时间范围。"
                    "请补充具体日期、日期区间或明确的自然时间周期。"
                ),
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

    @staticmethod
    def _identity_clarification(binding: CustomerBinding, model: str) -> CRMQueryAgentResult:
        if binding.status == "AMBIGUOUS":
            names = "、".join(ref.display_name for ref in binding.candidates[:5])
            question = f"请确认你要查询哪家客户\uff1a{names}。"
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
