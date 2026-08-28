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


def test_customer_scoped_classifier_does_not_bind_city_customer_list() -> None:
    binder = CustomerQueryIdentityBinder(identity_service=FakeIdentityService("no_match", []))

    assert binder.classify("上海有哪些客户") is None


def test_customer_scoped_classifier_extracts_full_name_and_resource() -> None:
    binder = CustomerQueryIdentityBinder(identity_service=FakeIdentityService("no_match", []))

    intent = binder.classify("广东智通人才连锁股份有限公司有哪些商机?")

    assert intent == CustomerQueryIntent(
        tool_name="get_customer_context",
        customer_text="广东智通人才连锁股份有限公司",
    )


def test_binder_uses_authorized_identity_resolution_and_issues_entity_ref() -> None:
    service = FakeIdentityService(
        "auto_select",
        [{"id": "cus_1", "account_name": "凡亚信息", "city": "广州"}],
    )
    binder = CustomerQueryIdentityBinder(identity_service=service)

    intent = binder.classify("凡亚信息有哪些联系人?")
    assert intent is not None
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
