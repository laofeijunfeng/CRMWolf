from __future__ import annotations

import pytest

from app.services.agent.orchestrator.contracts import QueryExecutionInput, RootRuntimeContext
from app.services.agent.orchestrator.query_executor import CRMQueryAgentExecutor
from app.services.agent.principal import AgentPrincipal
from app.services.agent.query import (
    CRMQueryAgentModelConfig,
    CRMQueryAgentResponse,
    CRMQueryAgentResult,
    CRMQueryAgentTrace,
    EntityRef,
)
from app.services.agent.query.identity import (
    CustomerBinding,
    CustomerQueryIdentityBinder,
    CustomerQueryIntent,
)
from app.services.agent.query.semantic_intent import CRMQuerySemanticIntent, QueryTemporalIntent


class FakeIdentityService:
    def __init__(self, decision: str, items: list[dict[str, object]]) -> None:
        self.decision = decision
        self.items = items
        self.calls: list[dict[str, object]] = []

    def resolve(self, db: object, **kwargs: object):
        from app.services.customer_identity_resolution_service import CustomerIdentityResolution

        self.calls.append({"db": db, **kwargs})
        return CustomerIdentityResolution(
            items=self.items,
            related_customers=[],
            metadata={"identity_decision": self.decision},
        )


def _context() -> object:
    from app.services.agent.tools.base import AgentToolContext

    return AgentToolContext(
        db=object(),
        team_id=7,
        user_id=42,
        session_id=11,
        authorization="Bearer token",
        permission_codes=frozenset({"customer:read"}),
    )


def test_identity_binder_accepts_only_structured_customer_intent() -> None:
    binder = CustomerQueryIdentityBinder(identity_service=FakeIdentityService("no_match", []))

    binding = binder.bind(
        CustomerQueryIntent(
            tool_name="query_follow_up_tasks",
            customer_text="凡亚信息",
        ),
        _context(),
    )

    assert binding.status == "NOT_FOUND"



def test_binder_uses_authorized_identity_resolution_and_issues_entity_ref() -> None:
    service = FakeIdentityService(
        "auto_select",
        [{"id": "cus_1", "account_name": "凡亚信息", "city": "广州"}],
    )
    binder = CustomerQueryIdentityBinder(identity_service=service)

    intent = CustomerQueryIntent(tool_name="query_customer_contacts", customer_text="凡亚信息")
    binding = binder.bind(intent, _context())

    assert binding.status == "BOUND"
    assert binding.entity_ref == EntityRef(
        ref_id="eref_customer_cus_1",
        resource="customer",
        public_id="cus_1",
        display_name="凡亚信息",
    )
    assert service.calls[0]["query_text"] == "凡亚信息"
    assert service.calls[0]["team_id"] == 7
    assert service.calls[0]["user_id"] == 42


class StubSemanticIntentResolver:
    def __init__(self, intents: dict[str, CRMQuerySemanticIntent] | None = None) -> None:
        self.intents = intents or {}
        self.calls: list[str] = []

    async def resolve(self, text: str, **kwargs: object) -> CRMQuerySemanticIntent:
        self.calls.append(text)
        return self.intents.get(
            text,
            CRMQuerySemanticIntent(
                scope="customer_scoped",
                resource="customer_contacts",
                customer_text="凡亚信息",
                confidence=1,
            ),
        )


def _semantic_resolver() -> StubSemanticIntentResolver:
    return StubSemanticIntentResolver(
        {
            "这周有哪些事情要做": CRMQuerySemanticIntent(
                scope="global_work", resource="follow_up_tasks",
                temporal=QueryTemporalIntent(kind="this_week"), confidence=1,
            ),
            "下周需要跟进什么": CRMQuerySemanticIntent(
                scope="global_work", resource="follow_up_tasks",
                temporal=QueryTemporalIntent(kind="next_week"), confidence=1,
            ),
            "凡亚信息下周有哪些待办": CRMQuerySemanticIntent(
                scope="customer_scoped", resource="follow_up_tasks", customer_text="凡亚信息",
                temporal=QueryTemporalIntent(kind="next_week"), confidence=1,
            ),
            "当前客户这周有哪些待办": CRMQuerySemanticIntent(
                scope="customer_scoped", resource="follow_up_tasks",
                temporal=QueryTemporalIntent(kind="this_week"), confidence=1,
            ),
            "凡亚信息最近两周有哪些待办": CRMQuerySemanticIntent(
                scope="customer_scoped", resource="follow_up_tasks", customer_text="凡亚信息",
                temporal=QueryTemporalIntent(
                    kind="custom", start_at="2026-08-24", end_at="2026-09-07"
                ), confidence=1,
            ),
            "凡亚信息本月完成了什么": CRMQuerySemanticIntent(
                scope="customer_scoped", resource="completed_work", customer_text="凡亚信息",
                temporal=QueryTemporalIntent(kind="this_month"), confidence=1,
            ),
            "凡亚信息完成了什么": CRMQuerySemanticIntent(
                scope="customer_scoped", resource="completed_work", customer_text="凡亚信息",
                temporal=QueryTemporalIntent(kind="unspecified"), confidence=0.5,
            ),
            "未来两周有哪些事情要做": CRMQuerySemanticIntent(
                scope="global_work", resource="follow_up_tasks",
                temporal=QueryTemporalIntent(kind="unspecified"), confidence=0.3,
            ),
            "这周我完成了什么": CRMQuerySemanticIntent(
                scope="global_work", resource="completed_work",
                temporal=QueryTemporalIntent(kind="this_week"), confidence=1,
            ),
        }
    )


class RecordingQueryAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []

    async def run(self, request, tool_context, model_config) -> CRMQueryAgentResult:
        self.calls.append((request, tool_context, model_config))
        return CRMQueryAgentResult(
            response=CRMQueryAgentResponse(
                status="ANSWERED",
                answer="已查询",
                evidence_refs=["qry_1"],
            ),
            trace=CRMQueryAgentTrace(
                model="test-model",
                tool_names=["query_customer_contacts"],
                tool_call_count=1,
                total_entity_count=0,
                elapsed_ms=1,
                stop_reason="COMPLETED",
            ),
        )


class GlobalQueryBinder:
    def __init__(self) -> None:
        self.classify_calls: list[str] = []

    def classify(self, text: str):
        self.classify_calls.append(text)
        return None


class StubBinder:
    def __init__(self, binding: CustomerBinding | None) -> None:
        self.binding = binding
        self.classify_calls: list[str] = []
        self.bind_calls: list[tuple[CustomerQueryIntent, object]] = []

    def classify(self, text: str):
        self.classify_calls.append(text)
        return CustomerQueryIntent("query_customer_contacts", "凡亚信息")

    def bind(self, intent, context):
        self.bind_calls.append((intent, context))
        return self.binding


def _runtime() -> RootRuntimeContext:
    return RootRuntimeContext(
        db=object(),
        authorization="Bearer token",
        query_model_config=CRMQueryAgentModelConfig(
            api_host="https://ai.example.com/v1",
            api_key="key",
            model="test-model",
            temperature=0,
        ),
    )


@pytest.mark.asyncio
async def test_query_execution_marks_task_reference_search_on_server_context() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="找一下发送方案的待办",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
            semantic_intent=CRMQuerySemanticIntent(
                scope="global_work",
                resource="follow_up_tasks",
                query_goal="search",
                task_text="发送方案",
                confidence=0.95,
            ),
        ),
        runtime=_runtime(),
    )

    _request, tool_context, _model_config = query_agent.calls[0]
    assert tool_context.query_retrieval_mode == "semantic_filter"


@pytest.mark.asyncio
async def test_query_execution_reuses_root_semantic_intent_without_resolving_again() -> None:
    query_agent = RecordingQueryAgent()
    resolver = _semantic_resolver()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=resolver,
    )

    result = await executor.execute(
        QueryExecutionInput(
            text="这周有哪些事情要做",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
            semantic_intent=CRMQuerySemanticIntent(
                scope="global_work",
                resource="follow_up_tasks",
                temporal=QueryTemporalIntent(kind="this_week"),
                confidence=0.95,
            ),
        ),
        runtime=_runtime(),
    )

    assert result.response.status == "ANSWERED"
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_unknown_semantic_intent_fails_closed_without_query_agent_call() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )

    result = await executor.execute(
        QueryExecutionInput(
            text="帮我看看最近的情况",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
            semantic_intent=CRMQuerySemanticIntent(scope="unknown", confidence=0.35),
        ),
        runtime=_runtime(),
    )

    assert result.response.status == "CLARIFICATION_REQUIRED"
    assert result.response.clarification_question
    assert query_agent.calls == []


@pytest.mark.asyncio
async def test_customer_list_semantic_intent_restricts_query_agent_to_customer_list() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="上海有哪些客户",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
            semantic_intent=CRMQuerySemanticIntent(
                scope="customer_list", resource="customers", confidence=0.96
            ),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.allowed_tool_names == ["query_customers"]



@pytest.mark.asyncio
async def test_query_execution_binds_customer_before_model_and_restricts_tool_surface() -> None:
    customer_ref = EntityRef(
        ref_id="eref_customer_cus_1",
        resource="customer",
        public_id="cus_1",
        display_name="凡亚信息",
    )
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=StubBinder(CustomerBinding(status="BOUND", entity_ref=customer_ref)),
        semantic_intent_resolver=_semantic_resolver(),
    )

    result = await executor.execute(
        QueryExecutionInput(
            text="凡亚信息有哪些联系人?",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.entity_refs == [customer_ref]
    assert request.allowed_tool_names == ["query_customer_contacts"]
    assert result.authoritative_entity_refs == [customer_ref]


@pytest.mark.asyncio
async def test_query_execution_stops_on_ambiguous_identity_without_model_call() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=StubBinder(
            CustomerBinding(
                status="AMBIGUOUS",
                candidates=(
                    EntityRef(
                        ref_id="eref_customer_1",
                        resource="customer",
                        public_id="cus_1",
                        display_name="广州凡亚信息",
                    ),
                    EntityRef(
                        ref_id="eref_customer_2",
                        resource="customer",
                        public_id="cus_2",
                        display_name="深圳凡亚信息",
                    ),
                ),
                query_text="凡亚信息",
            )
        ),
        semantic_intent_resolver=_semantic_resolver(),
    )

    result = await executor.execute(
        QueryExecutionInput(
            text="凡亚信息有哪些联系人?",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    assert result.response.status == "CLARIFICATION_REQUIRED"
    assert "广州凡亚信息" in (result.response.clarification_question or "")
    assert "深圳凡亚信息" in (result.response.clarification_question or "")
    assert query_agent.calls == []


@pytest.mark.asyncio
async def test_selected_customer_query_keeps_customer_scope_and_applies_temporal_filter() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )
    selected_customer = EntityRef(
        ref_id="eref_customer_selected",
        resource="customer",
        public_id="cus_selected",
        display_name="凡亚信息",
    )

    await executor.execute(
        QueryExecutionInput(
            text="这周有哪些待办",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
            selected_entity=selected_customer,
            semantic_intent=CRMQuerySemanticIntent(
                scope="customer_scoped",
                resource="follow_up_tasks",
                temporal=QueryTemporalIntent(kind="this_week"),
                confidence=1,
            ),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.entity_refs == [selected_customer]
    assert request.allowed_tool_names == ["query_follow_up_tasks"]
    assert [filter_.model_dump() for filter_ in request.authoritative_filters] == [
        {"field": "status", "operator": "eq", "value": "open"},
        {"field": "due_window", "operator": "eq", "value": "this_week"},
    ]


@pytest.mark.asyncio
async def test_selected_customer_query_resolves_semantics_when_root_did_not_supply_intent() -> None:
    query_agent = RecordingQueryAgent()
    resolver = _semantic_resolver()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=resolver,
    )
    selected_customer = EntityRef(
        ref_id="eref_customer_selected",
        resource="customer",
        public_id="cus_selected",
        display_name="凡亚信息",
    )

    await executor.execute(
        QueryExecutionInput(
            text="当前客户这周有哪些待办",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
            selected_entity=selected_customer,
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert resolver.calls == ["当前客户这周有哪些待办"]
    assert request.entity_refs == [selected_customer]
    assert request.allowed_tool_names == ["query_follow_up_tasks"]
    assert [filter_.model_dump() for filter_ in request.authoritative_filters] == [
        {"field": "status", "operator": "eq", "value": "open"},
        {"field": "due_window", "operator": "eq", "value": "this_week"},
    ]


@pytest.mark.asyncio
async def test_global_follow_up_query_restricts_query_agent_to_follow_up_tasks() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="这周有哪些事情要做",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.allowed_tool_names == ["query_follow_up_tasks"]
    assert request.authoritative_scope == "mine"
    assert [filter_.model_dump() for filter_ in request.authoritative_filters] == [
        {"field": "status", "operator": "eq", "value": "open"},
        {"field": "due_window", "operator": "eq", "value": "this_week"},
    ]


@pytest.mark.asyncio
async def test_global_follow_up_query_uses_the_detected_next_week_window() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="下周需要跟进什么",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.authoritative_filters[-1].model_dump() == {
        "field": "due_window",
        "operator": "eq",
        "value": "next_week",
    }


@pytest.mark.asyncio
async def test_unsupported_global_work_window_fails_closed_without_model_call() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )

    result = await executor.execute(
        QueryExecutionInput(
            text="未来两周有哪些事情要做",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    assert result.response.status == "CLARIFICATION_REQUIRED"
    assert "还不能确定你要查询哪类 CRM 信息" in (result.response.clarification_question or "")
    assert result.trace.stop_reason == "CLARIFICATION_REQUIRED"
    assert query_agent.calls == []


@pytest.mark.asyncio
async def test_global_completed_work_query_restricts_query_agent_to_completed_work() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=GlobalQueryBinder(),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="这周我完成了什么",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.allowed_tool_names == ["query_completed_work"]
    assert request.authoritative_scope == "mine"
    assert [filter_.model_dump() for filter_ in request.authoritative_filters] == [
        {"field": "window", "operator": "eq", "value": "this_week"},
    ]


@pytest.mark.asyncio
async def test_customer_follow_up_query_authoritatively_applies_customer_time_window() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=StubBinder(
            CustomerBinding(
                status="BOUND",
                entity_ref=EntityRef(
                    ref_id="eref_customer_cus_1",
                    resource="customer",
                    public_id="cus_1",
                    display_name="凡亚信息",
                ),
            )
        ),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="凡亚信息下周有哪些待办",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.allowed_tool_names == ["query_follow_up_tasks"]
    assert request.authoritative_scope is None
    assert [filter_.model_dump() for filter_ in request.authoritative_filters] == [
        {"field": "status", "operator": "eq", "value": "open"},
        {"field": "due_window", "operator": "eq", "value": "next_week"},
    ]


@pytest.mark.asyncio
async def test_customer_follow_up_query_authoritatively_applies_custom_time_range() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=StubBinder(
            CustomerBinding(
                status="BOUND",
                entity_ref=EntityRef(
                    ref_id="eref_customer_cus_1",
                    resource="customer",
                    public_id="cus_1",
                    display_name="凡亚信息",
                ),
            )
        ),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="凡亚信息最近两周有哪些待办",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert [filter_.model_dump() for filter_ in request.authoritative_filters] == [
        {"field": "status", "operator": "eq", "value": "open"},
        {
            "field": "tracking_time",
            "operator": "between",
            "value": ["2026-08-24", "2026-09-07"],
        },
    ]


@pytest.mark.asyncio
async def test_customer_completed_work_query_authoritatively_applies_time_window() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=StubBinder(
            CustomerBinding(
                status="BOUND",
                entity_ref=EntityRef(
                    ref_id="eref_customer_cus_1",
                    resource="customer",
                    public_id="cus_1",
                    display_name="凡亚信息",
                ),
            )
        ),
        semantic_intent_resolver=_semantic_resolver(),
    )

    await executor.execute(
        QueryExecutionInput(
            text="凡亚信息本月完成了什么",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    request, _context_value, _model_config = query_agent.calls[0]
    assert request.allowed_tool_names == ["query_completed_work"]
    assert [filter_.model_dump() for filter_ in request.authoritative_filters] == [
        {"field": "window", "operator": "eq", "value": "this_month"},
    ]


@pytest.mark.asyncio
async def test_customer_completed_work_without_time_does_not_use_api_this_week_default() -> None:
    query_agent = RecordingQueryAgent()
    executor = CRMQueryAgentExecutor(
        query_agent=query_agent,
        identity_binder=StubBinder(
            CustomerBinding(
                status="BOUND",
                entity_ref=EntityRef(
                    ref_id="eref_customer_cus_1",
                    resource="customer",
                    public_id="cus_1",
                    display_name="凡亚信息",
                ),
            )
        ),
        semantic_intent_resolver=_semantic_resolver(),
    )

    result = await executor.execute(
        QueryExecutionInput(
            text="凡亚信息完成了什么",
            principal=AgentPrincipal(team_id=7, user_id=42, session_id=11),
        ),
        runtime=_runtime(),
    )

    assert result.response.status == "CLARIFICATION_REQUIRED"
    assert query_agent.calls == []
