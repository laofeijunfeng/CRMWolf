"""Agent lead/customer create payloads and missing-field copy require 产品."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.product_intent import EMPTY_CATALOG_MESSAGE
from app.models.lead import FollowUpMethod
from app.models.product import Product, ProductModule
from app.services.agent.business_rules import (
    format_customer_missing_fields,
    format_lead_missing_fields,
    missing_customer_fields,
    missing_lead_fields,
)
from app.services.agent.principal import AgentPrincipal
from app.services.agent.tool_registry import AgentCustomerCreatePayload, AgentLeadCreatePayload
from app.services.agent.workflow.contracts import WorkflowTextStart, WorkflowTurnInput
from app.services.agent.workflow.planning import CRMWorkflowPlanner, WorkflowPlanningNeedsInput


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-lead-customer-product.db'}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=OFF")

    Base.metadata.create_all(engine, tables=[Product.__table__, ProductModule.__table__])
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _lead_kwargs(**overrides) -> dict:
    payload = {
        "lead_name": "A",
        "city": "上海",
        "contact_name": "王",
        "contact_phone": "13800138000",
    }
    payload.update(overrides)
    return payload


def _customer_kwargs(**overrides) -> dict:
    payload = {"account_name": "A", "city": "上海"}
    payload.update(overrides)
    return payload


def test_agent_lead_create_payload_requires_product_public_id():
    with pytest.raises(ValidationError):
        AgentLeadCreatePayload(**_lead_kwargs())
    with pytest.raises(ValidationError):
        AgentLeadCreatePayload(**_lead_kwargs(product_public_id=""))
    payload = AgentLeadCreatePayload(**_lead_kwargs(product_public_id="prd_1"))
    assert payload.product_public_id == "prd_1"
    assert not hasattr(payload, "product_module_public_ids")


def test_agent_customer_create_payload_requires_product_public_id():
    with pytest.raises(ValidationError):
        AgentCustomerCreatePayload(**_customer_kwargs())
    with pytest.raises(ValidationError):
        AgentCustomerCreatePayload(**_customer_kwargs(product_public_id=""))
    payload = AgentCustomerCreatePayload(**_customer_kwargs(product_public_id="prd_1"))
    assert payload.product_public_id == "prd_1"
    assert not hasattr(payload, "product_module_public_ids")


def test_missing_lead_fields_includes_product_public_id():
    assert "product_public_id" in missing_lead_fields(_lead_kwargs())
    assert "product_public_id" not in missing_lead_fields(_lead_kwargs(product_public_id="prd_1"))


def test_missing_customer_fields_always_requires_product_public_id():
    assert "product_public_id" in missing_customer_fields(_customer_kwargs())
    with_contact = _customer_kwargs(
        contact_name="王",
        contact_phone="13800138000",
        contact_position="CTO",
        contact_gender="1",
    )
    assert "product_public_id" in missing_customer_fields(with_contact)
    assert "product_public_id" not in missing_customer_fields(
        _customer_kwargs(product_public_id="prd_1")
    )


def test_format_lead_missing_fields_labels_product_not_module():
    assert format_lead_missing_fields(["product_public_id"]) == "产品"
    assert "模块" not in format_lead_missing_fields(["product_public_id"])


def test_format_customer_missing_fields_labels_product_not_module():
    assert format_customer_missing_fields(["product_public_id"]) == "产品"
    assert "模块" not in format_customer_missing_fields(["product_public_id"])


def _plan_lead(
    semantic_lead: SimpleNamespace,
    *,
    db: object,
    user_message: str | None = None,
    request: WorkflowTurnInput | None = None,
):
    planner = CRMWorkflowPlanner()
    return planner._plan_lead(
        SimpleNamespace(lead=semantic_lead),
        db=db,
        team_id=1,
        workflow_id="wf_lead_product",
        current_datetime=datetime(2026, 8, 23, 9, 0, 0),
        user_message=user_message,
        request=request,
    )


async def _plan_customer(semantic_customer: SimpleNamespace, *, db: object):
    planner = CRMWorkflowPlanner()
    return await planner._plan_customer(
        SimpleNamespace(customer_create=semantic_customer),
        db=db,
        team_id=1,
        workflow_id="wf_customer_product",
        current_datetime=datetime(2026, 8, 23, 9, 0, 0),
    )


def test_plan_lead_copies_product_public_id_and_omits_modules():
    plan = _plan_lead(SimpleNamespace(**_lead_kwargs(product_public_id="prd_1")), db=object())
    lead = plan.commands[0].payload["lead"]
    assert lead["product_public_id"] == "prd_1"
    assert "product_module_public_ids" not in lead
    assert "模块" not in (plan.interaction.prompt if plan.interaction else "")


def test_plan_lead_missing_product_asks_for_product_not_raw_public_id():
    with pytest.raises(WorkflowPlanningNeedsInput) as exc:
        _plan_lead(SimpleNamespace(**_lead_kwargs()), db=object())
    prompt = exc.value.interaction.prompt
    assert "产品" in prompt
    assert "product_public_id" not in prompt
    assert "模块" not in prompt
    assert "团队还没有可用产品" not in prompt


def test_plan_lead_empty_catalog_appends_admin_copy(db):
    with pytest.raises(WorkflowPlanningNeedsInput) as exc:
        _plan_lead(SimpleNamespace(**_lead_kwargs()), db=db)
    prompt = exc.value.interaction.prompt
    assert "产品" in prompt
    assert EMPTY_CATALOG_MESSAGE in prompt
    assert "product_public_id" not in prompt
    assert "模块" not in prompt

def test_plan_lead_resolves_product_name_to_public_id(db):
    from app.crud.product import product_crud
    from app.schemas.product import ProductCreate

    product = product_crud.create(db, 1, ProductCreate(name="Hifox"), "u1")
    plan = _plan_lead(SimpleNamespace(**_lead_kwargs(product_public_id="Hifox")), db=db)
    assert plan.commands[0].payload["lead"]["product_public_id"] == product.public_id

def test_plan_lead_matches_product_name_from_user_message(db):
    from app.crud.product import product_crud
    from app.schemas.product import ProductCreate

    product = product_crud.create(db, 1, ProductCreate(name="Hifox"), "u1")
    plan = _plan_lead(
        SimpleNamespace(**_lead_kwargs()),
        db=db,
        user_message="录入 Hifox 线索\n企业名称：协鑫数智科技\n联系人：黄思盛",
    )
    assert plan.commands[0].payload["lead"]["product_public_id"] == product.public_id




@pytest.mark.asyncio
async def test_plan_customer_copies_product_public_id_and_omits_modules():
    plan = await _plan_customer(
        SimpleNamespace(**_customer_kwargs(product_public_id="prd_1")),
        db=object(),
    )
    customer = plan.commands[0].payload["customer"]
    assert customer["product_public_id"] == "prd_1"
    assert "product_module_public_ids" not in customer
    assert "模块" not in (plan.interaction.prompt if plan.interaction else "")


@pytest.mark.asyncio
async def test_plan_customer_missing_product_asks_for_product_not_raw_public_id():
    with pytest.raises(WorkflowPlanningNeedsInput) as exc:
        await _plan_customer(SimpleNamespace(**_customer_kwargs()), db=object())
    prompt = exc.value.interaction.prompt
    assert "产品" in prompt
    assert "product_public_id" not in prompt
    assert "模块" not in prompt
    assert "团队还没有可用产品" not in prompt


@pytest.mark.asyncio
async def test_plan_customer_empty_catalog_appends_admin_copy(db):
    with pytest.raises(WorkflowPlanningNeedsInput) as exc:
        await _plan_customer(SimpleNamespace(**_customer_kwargs()), db=db)
    prompt = exc.value.interaction.prompt
    assert "产品" in prompt
    assert EMPTY_CATALOG_MESSAGE in prompt
    assert "product_public_id" not in prompt
    assert "模块" not in prompt


def test_plan_lead_defaults_blank_follow_up_method_to_other():
    plan = _plan_lead(
        SimpleNamespace(**_lead_kwargs(product_public_id="prd_1"), follow_up_content="已电话沟通"),
        db=object(),
    )
    assert plan.commands[1].payload["method"] == FollowUpMethod.OTHER.value


def test_plan_lead_maps_online_meeting_method_to_other():
    plan = _plan_lead(
        SimpleNamespace(
            **_lead_kwargs(product_public_id="prd_1"),
            follow_up_content="开了线上会议",
            follow_up_method="线上会议",
        ),
        db=object(),
    )
    assert plan.commands[1].payload["method"] == FollowUpMethod.OTHER.value


def test_plan_lead_unmapped_method_asks_for_closed_choice():
    request = WorkflowTurnInput(
        workflow_id="wf_" + "a" * 32,
        start=WorkflowTextStart(kind="text", text="录入线索"),
        principal=AgentPrincipal(team_id=1, user_id=2, session_id=3),
    )
    with pytest.raises(WorkflowPlanningNeedsInput) as exc:
        _plan_lead(
            SimpleNamespace(
                **_lead_kwargs(product_public_id="prd_1"),
                follow_up_content="发了传真",
                follow_up_method="传真",
            ),
            db=object(),
            request=request,
        )
    interaction = exc.value.interaction
    assert interaction.interaction_type == "choice"
    assert interaction.business_action == "select_lead_follow_up_method"
    assert [option.value for option in interaction.options] == ["电话", "微信", "拜访", "邮件", "其他"]
    assert exc.value.checkpoint_request is request


def test_plan_lead_maps_tilde_scale_to_one_to_fifty():
    plan = _plan_lead(
        SimpleNamespace(**_lead_kwargs(product_public_id="prd_1", company_scale="10~29")),
        db=object(),
    )
    assert plan.commands[0].payload["lead"]["company_scale"] == "1-50人"


def test_create_lead_follow_up_input_rejects_unmapped_method():
    from app.services.agent.tool_registry import CreateLeadFollowUpInput

    with pytest.raises(ValidationError):
        CreateLeadFollowUpInput(lead_id="lead_001", content="跟进", method="线上会议")
