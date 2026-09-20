from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import customers as customers_api
from app.api import customer_ai as customer_ai_api
from app.services.ai_parser import customer_parser as customer_parser_module
from app.services.ai_parser.customer_parser import CustomerAIParser

from app.schemas.customer import ConvertLeadToCustomer

from unittest.mock import MagicMock


class _RequestData(SimpleNamespace):
    def model_copy(self, *, update=None):
        values = vars(self).copy()
        values.update(update or {})
        return type(self)(**values)


@pytest.fixture
def customer_and_user():
    return (
        SimpleNamespace(
            id=101,
            public_id="cus_101",
            account_name="客户A",
            owner_id="9",
            team_id=2,
            version=1,
        ),
        SimpleNamespace(id=9, name="管理员"),
    )


def test_add_customer_member_uses_unified_created_event(monkeypatch, customer_and_user):
    customer, user = customer_and_user
    member = SimpleNamespace(
        id=301,
        team_id=2,
        customer_id=101,
        user_id="12",
        member_role="PRESALES",
        access_level="VIEW",
        remark="协同",
        is_active=True,
    )
    calls = []

    monkeypatch.setattr(customers_api, "check_customer_member_manage_permission", lambda *args: customer)
    monkeypatch.setattr(customers_api.team_crud, "is_member", lambda *args: True)
    monkeypatch.setattr(customers_api.customer_member_crud, "create_or_restore", lambda **kwargs: member)
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(scheduled=True),
    )
    monkeypatch.setattr(customers_api, "_build_customer_member_response", lambda *args: member)

    result = customers_api.add_customer_member(
        "cus_101",
        _RequestData(user_id=12, member_role="PRESALES", access_level="VIEW", remark="协同"),
        team_id=2,
        current_user=user,
        db=object(),
    )

    assert result is member
    assert calls[0]["business_object"] is member
    assert calls[0]["source_type"] == "customer_member"
    assert calls[0]["change_type"] == "created"
    assert calls[0]["actor_id"] == "9"


def test_update_customer_member_uses_unified_updated_event(monkeypatch, customer_and_user):
    customer, user = customer_and_user
    member = SimpleNamespace(
        id=301,
        team_id=2,
        customer_id=101,
        user_id="12",
        member_role="PRESALES",
        access_level="VIEW",
        remark="协同",
        is_active=True,
    )
    calls = []

    monkeypatch.setattr(customers_api, "check_customer_member_manage_permission", lambda *args: customer)
    monkeypatch.setattr(customers_api.customer_member_crud, "get_by_id", lambda *args: member)
    monkeypatch.setattr(customers_api.customer_member_crud, "update", lambda *args: member)
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(scheduled=True),
    )
    monkeypatch.setattr(customers_api, "_build_customer_member_response", lambda *args: member)

    result = customers_api.update_customer_member(
        "cus_101",
        301,
        _RequestData(member_role="SALES", access_level="FOLLOW_UP", remark="重点协同"),
        team_id=2,
        current_user=user,
        db=object(),
    )

    assert result is member
    assert calls[0]["business_object"] is member
    assert calls[0]["change_type"] == "updated"


def test_remove_customer_member_uses_unified_deleted_event(monkeypatch, customer_and_user):
    customer, user = customer_and_user
    member = SimpleNamespace(
        id=301,
        team_id=2,
        customer_id=101,
        user_id="12",
        member_role="PRESALES",
        access_level="VIEW",
        remark="协同",
        is_active=False,
    )
    calls = []

    monkeypatch.setattr(customers_api, "check_customer_member_manage_permission", lambda *args: customer)
    monkeypatch.setattr(customers_api.customer_member_crud, "get_by_id", lambda *args: member)
    monkeypatch.setattr(customers_api.customer_member_crud, "deactivate", lambda *args: None)
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(scheduled=True),
    )

    result = customers_api.remove_customer_member(
        "cus_101",
        301,
        team_id=2,
        current_user=user,
        db=object(),
    )

    assert result.message == "移除成功"
    assert calls[0]["business_object"] is member
    assert calls[0]["change_type"] == "deleted"


def _conversion_rows():
    lead = SimpleNamespace(id=44, public_id="lead_44", lead_name="线索客户")
    customer = SimpleNamespace(
        id=101,
        public_id="cus_101",
        account_name="线索客户",
        owner_id="9",
        team_id=2,
        version=1,
        industry=None,
    )
    contact = SimpleNamespace(id=301, name="李华")
    return lead, customer, contact


@pytest.mark.asyncio
async def test_legacy_conversion_uses_lifecycle_coordinator_after_commit(monkeypatch):
    lead, customer, contact = _conversion_rows()
    db = MagicMock()
    lifecycle_calls = []
    kick_calls = []
    work = SimpleNamespace(enrichment_request=None, profile_request=None, warnings=())

    monkeypatch.setattr(customers_api.lead_crud, "get_by_public_id", lambda *args: lead)
    monkeypatch.setattr(customers_api, "_ensure_customer_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "convert_from_lead",
        lambda **kwargs: (customer, contact),
    )
    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "enqueue_after_commit",
        lambda **kwargs: lifecycle_calls.append(kwargs) or work,
    )

    def fail_kick(value):
        kick_calls.append(value)
        raise RuntimeError("kick down")

    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "kick",
        fail_kick,
    )
    monkeypatch.setattr(
        customers_api.outbound_notification_job_service,
        "queue_committed",
        lambda *args, **kwargs: SimpleNamespace(id=1),
    )

    response = await customers_api.convert_from_lead(
        ConvertLeadToCustomer(lead_id="lead_44", product_public_id="prd_1"),
        team_id=2,
        current_user=SimpleNamespace(id=9, name="管理员"),
        db=db,
        operation_id=None,
        idempotency_key=None,
        correlation_id=None,
    )

    assert response.customer_id == "cus_101"
    assert lifecycle_calls == [
        {
            "customer": customer,
            "actor_id": "9",
            "trigger_type": "customer_converted_from_lead",
            "source_lead_id": 44,
        }
    ]
    assert kick_calls == [work]


@pytest.mark.asyncio
async def test_modern_conversion_prepares_before_commit_and_kicks_after(monkeypatch):
    lead, customer, contact = _conversion_rows()
    order: list[str] = []
    db = MagicMock()
    db.commit.side_effect = lambda: order.append("commit")
    execution = SimpleNamespace(operation_id="op_1", result_json=None)
    work = SimpleNamespace(enrichment_request=None, profile_request=None, warnings=())
    lifecycle_calls = []

    monkeypatch.setattr(
        customers_api.command_execution_service,
        "begin",
        lambda *args, **kwargs: (execution, False),
    )
    monkeypatch.setattr(customers_api.lead_crud, "get_by_public_id", lambda *args: lead)
    monkeypatch.setattr(customers_api, "_ensure_customer_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "convert_from_lead",
        lambda **kwargs: (customer, contact),
    )

    def succeed(db_session, execution_row, *, data, **kwargs):
        execution_row.result_json = {"data": data}

    monkeypatch.setattr(customers_api.command_execution_service, "succeed", succeed)
    monkeypatch.setattr(
        customers_api.command_execution_service,
        "to_response_payload",
        lambda value: {"operation_id": value.operation_id, "status": "SUCCEEDED", **value.result_json},
    )

    def prepare(db_session, **kwargs):
        order.append("prepare")
        lifecycle_calls.append(kwargs)
        return work

    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "prepare_in_transaction",
        prepare,
    )
    monkeypatch.setattr(
        customers_api.customer_lifecycle_post_commit_coordinator,
        "kick",
        lambda value: order.append("kick") or (),
    )
    monkeypatch.setattr(
        customers_api.outbound_notification_job_service,
        "queue_committed",
        lambda *args, **kwargs: SimpleNamespace(id=1),
    )

    response = await customers_api.convert_from_lead(
        ConvertLeadToCustomer(lead_id="lead_44", product_public_id="prd_1"),
        team_id=2,
        current_user=SimpleNamespace(id=9, name="管理员"),
        db=db,
        operation_id="op_1",
        idempotency_key="idem_1",
        correlation_id=None,
    )

    assert response.customer_id == "cus_101"
    assert order == ["prepare", "commit", "kick"]
    assert lifecycle_calls == [
        {
            "customer": customer,
            "actor_id": "9",
            "trigger_type": "customer_converted_from_lead",
            "source_lead_id": 44,
        }
    ]


@pytest.mark.asyncio
async def test_customer_ai_submit_uses_lifecycle_coordinator(monkeypatch):
    customer = SimpleNamespace(
        id=101,
        public_id="cus_101",
        account_name="AI客户",
        city="上海",
        status=1,
        team_id=2,
        industry=None,
    )
    parser = SimpleNamespace()
    parser.create_entity = lambda **kwargs: None
    parser.post_create_actions = lambda **kwargs: None

    async def create_entity(**kwargs):
        return customer

    async def post_create_actions(**kwargs):
        return None

    parser.create_entity = create_entity
    parser.post_create_actions = post_create_actions
    work = SimpleNamespace(enrichment_request=None, profile_request=None, warnings=())
    lifecycle_calls = []
    kick_calls = []
    monkeypatch.setattr(customer_ai_api.EntityAIParserFactory, "get_parser", lambda kind: parser)
    monkeypatch.setattr(customer_ai_api, "_ensure_customer_name_available", lambda *args: None)
    monkeypatch.setattr(
        customer_ai_api.customer_lifecycle_post_commit_coordinator,
        "enqueue_after_commit",
        lambda **kwargs: lifecycle_calls.append(kwargs) or work,
    )

    def fail_ai_kick(value):
        kick_calls.append(value)
        raise RuntimeError("kick down")

    monkeypatch.setattr(
        customer_ai_api.customer_lifecycle_post_commit_coordinator,
        "kick",
        fail_ai_kick,
    )
    payload = SimpleNamespace(
        customer_info=SimpleNamespace(account_name="AI客户", model_dump=lambda: {"account_name": "AI客户"}),
        contact_info=SimpleNamespace(model_dump=lambda: {"contact_name": "李华"}),
        follow_up_info=None,
    )

    result = await customer_ai_api.create_customer_from_ai(
        payload,
        current_user=SimpleNamespace(id=9),
        team_id=2,
        db=object(),
    )

    assert result["public_id"] == "cus_101"
    assert lifecycle_calls == [
        {
            "customer": customer,
            "actor_id": "9",
            "trigger_type": "customer_created",
        }
    ]
    assert kick_calls == [work]


@pytest.mark.asyncio
async def test_customer_parser_post_create_actions_does_not_trigger_profile_refresh(monkeypatch):
    parser = CustomerAIParser()
    refresh_calls = []
    monkeypatch.setattr(
        customer_parser_module,
        "customer_intelligence_refresh_service",
        SimpleNamespace(trigger_customer_created_refresh=lambda *args, **kwargs: refresh_calls.append(kwargs)),
        raising=False,
    )

    await parser.post_create_actions(
        db=object(),
        entity=SimpleNamespace(id=101, public_id="cus_101"),
        parsed_data={"follow_up_info": None},
        user_id="9",
        team_id=2,
    )

    assert refresh_calls == []
