"""Opportunity create defaults from customer intent product."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.product import product_crud
from app.crud.product_intent import EMPTY_CATALOG_MESSAGE
from app.models.customer import Customer, CustomerProduct
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.schemas.product import ProductCreate
from app.services.agent.business_rules import (
    apply_customer_opportunity_product_defaults,
    customer_opportunity_product_defaults,
    opportunity_field_defaults,
    opportunity_next_task_from_suggestions,
)
from app.services.agent.principal import AgentPrincipal
from app.services.agent.workflow.contracts import (
    WorkflowRuntimeContext,
    WorkflowTextStart,
    WorkflowTurnInput,
)
from app.services.agent.workflow.planning import CRMWorkflowPlanner, WorkflowPlanningNeedsInput
from app.services.agent.workflow.resources import ProcurementMethodResolution


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"



@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'opportunity-product-defaults.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=OFF")

    tables = [
        Product.__table__,
        ProductModule.__table__,
        Customer.__table__,
        CustomerProduct.__table__,
        Opportunity.__table__,
        OpportunityProductModule.__table__,
    ]
    renamed_indexes = []
    for table in tables:
        for index in table.indexes:
            if index.name:
                renamed_indexes.append((index, index.name))
                index.name = f"{table.name}_{index.name}"
    try:
        Base.metadata.create_all(engine, tables=tables)
    finally:
        for index, original_name in renamed_indexes:
            index.name = original_name
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def test_opportunity_field_defaults_use_customer_product_and_base():
    customer = {"id": "cus_1", "product_public_id": "prd_crm", "products": [{"public_id": "prd_crm", "name": "CRM"}]}
    defaults = opportunity_field_defaults(customer)
    assert defaults["product_public_id"] == "prd_crm"


def test_opportunity_field_defaults_keep_procurement_and_existing_module_ids():
    customer = {
        "id": "cus_1",
        "product_public_id": "prd_crm",
        "product_module_public_ids": ["prm_pro"],
        "default_procurement_method_id": 8,
    }
    defaults = opportunity_field_defaults(customer)
    assert defaults["product_public_id"] == "prd_crm"
    assert defaults["product_module_public_ids"] == ["prm_pro"]
    assert defaults["procurement_method_id"] == 8


def test_opportunity_field_defaults_without_product_keep_procurement_only():
    defaults = opportunity_field_defaults({"id": "cus_1", "default_procurement_method_id": 3})
    assert defaults == {"procurement_method_id": 3}


def test_customer_opportunity_product_defaults_use_customer_product_and_base(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    defaults = customer_opportunity_product_defaults(
        db,
        1,
        {"product_public_id": oa.public_id},
    )
    assert defaults["product_public_id"] == oa.public_id
    assert defaults["product_module_public_ids"] == [oa.modules[0].public_id]
    assert defaults["product_public_id"] != crm.public_id


def test_customer_opportunity_product_defaults_fall_back_when_intent_inactive(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    oa.is_active = False
    db.commit()
    defaults = customer_opportunity_product_defaults(
        db,
        1,
        {"product_public_id": oa.public_id},
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == [crm.modules[0].public_id]


def test_customer_opportunity_product_defaults_fall_back_when_intent_missing(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    defaults = customer_opportunity_product_defaults(
        db,
        1,
        {"product_public_id": "prd_gone"},
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == [crm.modules[0].public_id]


def test_customer_opportunity_product_defaults_empty_catalog_returns_empty(db):
    assert customer_opportunity_product_defaults(db, 1, {"product_public_id": "prd_crm"}) == {}
    assert customer_opportunity_product_defaults(db, 1, {}) == {}


def test_opportunity_field_defaults_merge_db_helper_when_team_available(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    defaults = opportunity_field_defaults(
        {"id": "cus_1", "default_procurement_method_id": 3},
        db=db,
        team_id=1,
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == [crm.modules[0].public_id]
    assert defaults["procurement_method_id"] == 3


def test_opportunity_field_defaults_keep_customer_modules_when_db_fills_base(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    defaults = opportunity_field_defaults(
        {
            "id": "cus_1",
            "product_public_id": crm.public_id,
            "product_module_public_ids": ["prm_keep"],
        },
        db=db,
        team_id=1,
    )
    assert defaults["product_public_id"] == crm.public_id
    assert defaults["product_module_public_ids"] == ["prm_keep"]


def test_apply_customer_opportunity_product_defaults_fills_intent_and_base(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    opportunity = {
        "total_amount": 100000,
        "user_count": 20,
        "license_type": "PERPETUAL",
        "purchase_type": "NEW",
        "expected_closing_date": "2026-09-01",
    }
    apply_customer_opportunity_product_defaults(
        opportunity,
        {"product_public_id": oa.public_id},
        db,
        1,
    )
    assert opportunity["product_public_id"] == oa.public_id
    assert opportunity["product_module_public_ids"] == [oa.modules[0].public_id]
    assert opportunity["product_public_id"] != crm.public_id


def test_apply_customer_opportunity_product_defaults_keeps_user_product(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    opportunity = {
        "product_public_id": crm.public_id,
        "product_module_public_ids": [crm.modules[0].public_id],
    }
    apply_customer_opportunity_product_defaults(
        opportunity,
        {"product_public_id": oa.public_id},
        db,
        1,
    )
    assert opportunity["product_public_id"] == crm.public_id
    assert opportunity["product_module_public_ids"] == [crm.modules[0].public_id]


def test_opportunity_next_task_copies_customer_product_into_payload():
    suggestion = SimpleNamespace(action="CREATE_OPPORTUNITY", confidence=0.9, title="创建商机")
    next_task = opportunity_next_task_from_suggestions(
        [suggestion],
        {
            "opportunity": {
                "total_amount": 100000,
                "user_count": 20,
                "license_type": "PERPETUAL",
                "purchase_type": "NEW",
                "expected_closing_date": "2026-09-01",
            }
        },
        {
            "id": "cus_1",
            "product_public_id": "prd_crm",
            "product_module_public_ids": ["prm_base"],
        },
    )
    assert next_task is not None
    opportunity = next_task["payload"]["opportunity"]
    assert opportunity["product_public_id"] == "prd_crm"
    assert opportunity["product_module_public_ids"] == ["prm_base"]
    assert next_task["payload"]["field_defaults"]["product_public_id"] == "prd_crm"


def test_opportunity_next_task_fills_base_module_ids_from_db(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    suggestion = SimpleNamespace(action="CREATE_OPPORTUNITY", confidence=0.9, title="创建商机")
    next_task = opportunity_next_task_from_suggestions(
        [suggestion],
        {
            "opportunity": {
                "total_amount": 100000,
                "user_count": 20,
                "license_type": "PERPETUAL",
                "purchase_type": "NEW",
                "expected_closing_date": "2026-09-01",
            }
        },
        {"id": "cus_1", "product_public_id": crm.public_id},
        db=db,
        team_id=1,
    )
    assert next_task is not None
    opportunity = next_task["payload"]["opportunity"]
    assert opportunity["product_public_id"] == crm.public_id
    assert opportunity["product_module_public_ids"] == [crm.modules[0].public_id]
    assert next_task["payload"]["field_defaults"]["product_module_public_ids"] == [crm.modules[0].public_id]


def _opportunity_request() -> WorkflowTurnInput:
    return WorkflowTurnInput(
        workflow_id="wf_" + "a" * 32,
        start=WorkflowTextStart(kind="text", text="为当前客户创建商机"),
        principal=AgentPrincipal(team_id=1, user_id=2, session_id=3),
    )


class _ResolvedProcurement:
    async def resolve(self, **kwargs: object) -> ProcurementMethodResolution:
        return ProcurementMethodResolution(status="RESOLVED", method_id=8, method_name="公开招标")


def _customer_with_intent(db, product) -> Customer:
    customer = Customer(
        public_id="cus_intent_1",
        team_id=1,
        account_name="意向客户",
        city="上海",
        creator_id="u1",
    )
    db.add(customer)
    db.flush()
    db.add(CustomerProduct(customer_id=customer.id, product_id=product.id, team_id=1))
    db.commit()
    db.refresh(customer)
    return customer


def _complete_opportunity_fields() -> dict[str, object]:
    return {
        "total_amount": 100000,
        "user_count": 20,
        "license_type": "PERPETUAL",
        "purchase_type": "NEW",
        "expected_closing_date": "2026-09-01",
    }


@pytest.mark.asyncio
async def test_plan_opportunity_for_customer_defaults_intent_product_and_base(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    customer = _customer_with_intent(db, oa)
    planner = CRMWorkflowPlanner(
        opportunity_procurement_method_resolver=_ResolvedProcurement(),
    )
    request = _opportunity_request()
    plan = await planner._plan_opportunity_for_customer(
        customer_id=customer.public_id,
        customer_name=customer.account_name,
        opportunity=_complete_opportunity_fields(),
        request=request,
        workflow_id=request.workflow_id,
        runtime=WorkflowRuntimeContext(db=db, authorization="Bearer test"),
        require_confirmation=True,
    )
    payload = plan.commands[0].payload["opportunity"]
    assert payload["product_public_id"] == oa.public_id
    assert payload["product_module_public_ids"] == [oa.modules[0].public_id]
    assert payload["product_public_id"] != crm.public_id


@pytest.mark.asyncio
async def test_plan_opportunity_for_customer_keeps_semantic_product(db):
    crm = product_crud.create(db, 1, ProductCreate(name="CRM"), "u1")
    oa = product_crud.create(db, 1, ProductCreate(name="OA"), "u1")
    customer = _customer_with_intent(db, oa)
    planner = CRMWorkflowPlanner(
        opportunity_procurement_method_resolver=_ResolvedProcurement(),
    )
    request = _opportunity_request()
    plan = await planner._plan_opportunity_for_customer(
        customer_id=customer.public_id,
        customer_name=customer.account_name,
        opportunity={
            **_complete_opportunity_fields(),
            "product_public_id": crm.public_id,
            "product_module_public_ids": [crm.modules[0].public_id],
        },
        request=request,
        workflow_id=request.workflow_id,
        runtime=WorkflowRuntimeContext(db=db, authorization="Bearer test"),
        require_confirmation=True,
    )
    payload = plan.commands[0].payload["opportunity"]
    assert payload["product_public_id"] == crm.public_id
    assert payload["product_module_public_ids"] == [crm.modules[0].public_id]


@pytest.mark.asyncio
async def test_plan_opportunity_empty_catalog_keeps_missing_product(db):
    customer = Customer(
        public_id="cus_empty_1",
        team_id=1,
        account_name="空目录客户",
        city="上海",
        creator_id="u1",
    )
    db.add(customer)
    db.commit()
    planner = CRMWorkflowPlanner(
        opportunity_procurement_method_resolver=_ResolvedProcurement(),
    )
    request = _opportunity_request()
    with pytest.raises(WorkflowPlanningNeedsInput) as exc:
        await planner._plan_opportunity_for_customer(
            customer_id=customer.public_id,
            customer_name=customer.account_name,
            opportunity=_complete_opportunity_fields(),
            request=request,
            workflow_id=request.workflow_id,
            runtime=WorkflowRuntimeContext(db=db, authorization="Bearer test"),
            require_confirmation=True,
        )
    prompt = exc.value.interaction.prompt
    assert "产品" in prompt
    assert EMPTY_CATALOG_MESSAGE in prompt

