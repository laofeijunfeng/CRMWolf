"""Agent lead/customer create payloads and missing-field copy require 产品."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from contextlib import nullcontext

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


class _EmptyQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def options(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return None

    def all(self):
        return []


def _queryable_db() -> SimpleNamespace:
    return SimpleNamespace(query=lambda *_args, **_kwargs: _EmptyQuery(), begin_nested=nullcontext)


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


def test_plan_lead_with_follow_up_projects_confirmation_facts():
    plan = _plan_lead(
        SimpleNamespace(
            **_lead_kwargs(product_public_id="prd_1", company_scale="10~29"),
            follow_up_content="已确认需要安排产品演示",
            follow_up_method="电话",
            next_action="安排产品演示",
        ),
        db=object(),
    )
    assert plan.interaction is not None
    facts = {fact.key: fact.value for fact in plan.interaction.facts}
    assert facts["lead_name"] == "A"
    assert facts["follow_up_method"] == "电话"
    assert facts["follow_up_content"] == "已确认需要安排产品演示"
    assert facts["company_scale"] == "1-50人"
    assert facts["next_action"] == "安排产品演示"


def test_create_lead_follow_up_input_rejects_unmapped_method():
    from app.services.agent.tool_registry import CreateLeadFollowUpInput

    with pytest.raises(ValidationError):
        CreateLeadFollowUpInput(lead_id="lead_001", content="跟进", method="线上会议")


def test_plan_lead_follow_up_on_unique_existing_lead_does_not_recreate(monkeypatch):
    existing = SimpleNamespace(public_id="lead_existing", lead_name="A")
    monkeypatch.setattr(
        "app.services.agent.workflow.planning.lead_crud.get_by_name",
        lambda db, lead_name, team_id: existing,
    )
    db = _queryable_db()
    plan = _plan_lead(
        SimpleNamespace(
            **_lead_kwargs(product_public_id="prd_1"),
            follow_up_content="电话补充跟进",
            follow_up_method="电话",
        ),
        db=db,
    )
    assert [command.tool_name for command in plan.commands] == ["create_lead_follow_up"]
    assert plan.commands[0].payload["lead_id"] == "lead_existing"
    assert plan.interaction is not None
    assert plan.interaction.prompt == "确认为已有线索“A”记录跟进吗?"


def test_plan_lead_existing_without_follow_up_does_not_recreate(monkeypatch):
    existing = SimpleNamespace(public_id="lead_existing", lead_name="A")
    monkeypatch.setattr(
        "app.services.agent.workflow.planning.lead_crud.get_by_name",
        lambda db, lead_name, team_id: existing,
    )
    db = _queryable_db()
    from app.services.agent.workflow.planning import WorkflowPlanningError

    with pytest.raises(WorkflowPlanningError, match="已存在"):
        _plan_lead(SimpleNamespace(**_lead_kwargs(product_public_id="prd_1")), db=db)


@pytest.mark.asyncio
async def test_plan_customer_activity_on_unique_existing_customer_does_not_recreate(monkeypatch):
    existing = SimpleNamespace(public_id="cust_existing", account_name="A")
    monkeypatch.setattr(
        "app.services.agent.workflow.planning.customer_crud.get_by_name",
        lambda db, account_name, team_id: existing,
    )
    db = _queryable_db()

    async def _evaluate_with_metadata(*_args, **_kwargs):
        from app.services.agent.quality import AgentFollowUpQualityEnvelope
        from app.services.agent.schemas import AgentFollowUpQualityResult

        return AgentFollowUpQualityEnvelope(
            result=AgentFollowUpQualityResult(
                score=80,
                passed=True,
                reason="测试质量评估结果。",
                next_action_status="CLEAR",
            ),
            quality_source="test",
            model="test-model",
        )

    monkeypatch.setattr(
        "app.services.agent.workflow.planning.agent_follow_up_quality_evaluator.evaluate_with_metadata",
        _evaluate_with_metadata,
    )
    plan = await _plan_customer(
        SimpleNamespace(
            **_customer_kwargs(product_public_id="prd_1"),
            follow_up_content="电话补充跟进",
            follow_up_method="微信",
        ),
        db=db,
    )
    assert [command.tool_name for command in plan.commands] == ["create_customer_activity"]
    assert plan.commands[0].payload["customer_id"] == "cust_existing"
    assert plan.interaction is not None


@pytest.mark.asyncio
async def test_plan_customer_existing_without_activity_does_not_recreate(monkeypatch):
    existing = SimpleNamespace(public_id="cust_existing", account_name="A")
    monkeypatch.setattr(
        "app.services.agent.workflow.planning.customer_crud.get_by_name",
        lambda db, account_name, team_id: existing,
    )
    db = _queryable_db()
    from app.services.agent.workflow.planning import WorkflowPlanningError

    with pytest.raises(WorkflowPlanningError, match="已存在"):
        await _plan_customer(SimpleNamespace(**_customer_kwargs(product_public_id="prd_1")), db=db)
