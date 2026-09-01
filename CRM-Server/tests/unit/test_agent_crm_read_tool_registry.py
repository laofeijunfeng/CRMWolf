"""Behavioral tests for the Query Agent's isolated read-only tool surface."""

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.services.agent.query import CRMQueryResult, CRMQuerySpec, EntityRef
from app.services.agent.query.registry import (
    CRMReadToolRegistry,
    CustomerContextCoverage,
    CustomerContextRequest,
    CustomerContextResult,
)
from app.services.agent.tools.base import AgentToolContext


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, spec, context):
        self.calls.append((spec, context))
        return CRMQueryResult(
            query_id="qry_01",
            resource=spec.resource,
            status="EMPTY",
            rows=[],
            entity_refs=[],
            total=0,
        )


class FakeCustomerContextReader:
    def __init__(self) -> None:
        self.calls = []

    async def read(self, request, context):
        self.calls.append((request, context))
        return CustomerContextResult(
            customer_ref=request.customer_ref,
            sections={"profile": {"summary": "客户关注交付周期"}},
            citations=[],
            coverage=CustomerContextCoverage(
                requested=request.sections,
                returned=["profile"],
                unavailable=[section for section in request.sections if section != "profile"],
            ),
        )


def _context() -> AgentToolContext:
    return AgentToolContext(
        db=Mock(),
        team_id=7,
        user_id=42,
        session_id=11,
        authorization="Bearer signed-token",
    )


def test_registry_exposes_only_the_frozen_read_tools_and_no_write_tools() -> None:
    registry = CRMReadToolRegistry(FakeExecutor(), FakeCustomerContextReader())

    assert tuple(registry.list_specs()) == (
        "query_customers",
        "query_customer_contacts",
        "query_customer_activities",
        "query_customer_deployment_infos",
        "query_follow_up_tasks",
        "query_completed_work",
        "get_customer_context",
    )
    assert registry.write_tool_count == 0
    assert all(spec.is_write is False for spec in registry.list_specs().values())


@pytest.mark.asyncio
async def test_registry_dispatches_query_spec_only_to_its_bound_resource() -> None:
    executor = FakeExecutor()
    registry = CRMReadToolRegistry(executor, FakeCustomerContextReader())
    payload = CRMQuerySpec(resource="customer", projection=["public_id", "account_name"])

    result = await registry.execute("query_customers", _context(), payload.model_dump(mode="json"))

    assert result.resource == "customer"
    assert executor.calls[0][0] == payload

    with pytest.raises(ValueError, match="is bound to resource customer"):
        await registry.execute(
            "query_customers",
            _context(),
            CRMQuerySpec(resource="contact", projection=["id"]).model_dump(mode="json"),
        )


@pytest.mark.asyncio
async def test_registry_dispatches_customer_context_to_dedicated_reader() -> None:
    reader = FakeCustomerContextReader()
    registry = CRMReadToolRegistry(FakeExecutor(), reader)
    request = CustomerContextRequest(
        customer_ref=EntityRef(
            ref_id="eref_customer_cus_01",
            resource="customer",
            public_id="cus_01",
            display_name="示例客户",
        ),
        sections=["profile", "evidence"],
        question="客户最关注什么?",
    )

    result = await registry.execute(
        "get_customer_context",
        _context(),
        request.model_dump(mode="json"),
    )

    assert result.customer_ref.public_id == "cus_01"
    assert reader.calls[0][0] == request


def test_registry_builds_langchain_tools_from_the_same_closed_read_surface() -> None:
    registry = CRMReadToolRegistry(FakeExecutor(), FakeCustomerContextReader())

    tools = registry.to_langchain_tools(_context())

    assert [tool.name for tool in tools] == list(registry.list_specs())


def test_registry_describes_resource_specific_query_fields_to_the_model() -> None:
    registry = CRMReadToolRegistry(FakeExecutor(), FakeCustomerContextReader())

    description = registry.get("query_customers").description

    assert "resource 固定为 customer" in description
    assert "public_id" in description
    assert "account_name" in description
    assert "account_name(contains/eq)" in description
    assert "public_id(eq)" in description
    assert "city(eq/in)" in description
    assert "page_size 使用 50" in description
    assert "空结果后不得放宽条件或重复查询" in description
    assert "客户名称字段是 account_name，不是 name" in description
    assert "客户标识字段是 public_id，不是 id" in description


def test_registry_exposes_customer_deployment_read_tool() -> None:
    registry = CRMReadToolRegistry(FakeExecutor(), FakeCustomerContextReader())

    spec = registry.get("query_customer_deployment_infos")

    assert spec.resource == "deployment_info"
    assert "customer_id(eq)" in spec.description


def test_customer_context_contract_rejects_invalid_reference_sections_and_coverage() -> None:
    non_customer = EntityRef(
        ref_id="eref_contact_01",
        resource="contact",
        public_id="con_01",
        display_name="联系人",
    )
    customer = EntityRef(
        ref_id="eref_customer_01",
        resource="customer",
        public_id="cus_01",
        display_name="客户",
    )

    with pytest.raises(ValidationError):
        CustomerContextRequest(customer_ref=non_customer, sections=["profile"])
    with pytest.raises(ValidationError):
        CustomerContextRequest(customer_ref=customer, sections=[])
    with pytest.raises(ValidationError):
        CustomerContextCoverage(requested=["profile"], returned=[], unavailable=[])
