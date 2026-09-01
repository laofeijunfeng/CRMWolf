from __future__ import annotations

from datetime import datetime

import pytest

from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeRefreshInput,
    CustomerBusinessObjectIntelligenceService,
)


@pytest.mark.asyncio
async def test_business_object_intelligence_service_builds_business_readable_refresh(monkeypatch) -> None:
    calls = []

    async def fake_trigger(db, **kwargs):
        calls.append({"db": db, **kwargs})
        return object()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_event_publication_service.trigger_committed_event_refresh",
        fake_trigger,
    )
    service = CustomerBusinessObjectIntelligenceService()

    await service.trigger_change_refresh(
        object(),
        CustomerBusinessObjectChangeRefreshInput(
            team_id=2,
            customer_id=101,
            actor_id="9",
            source_type="payment_plan",
            source_id=501,
            change_type="updated",
            object_name="首付款",
            payload={"planned_amount": 50000},
        ),
    )

    assert calls[0]["event"].summary == "回款计划已更新: 首付款"
    assert calls[0]["event"].payload == {
        "planned_amount": 50000,
        "object_type": "payment_plan",
        "object_name": "首付款",
        "change_type": "updated",
        "refresh_scope": "partial",
    }
    assert "501" not in calls[0]["event"].summary


def test_business_object_intelligence_service_enqueues_sync_refresh(monkeypatch) -> None:
    calls = []

    def fake_persist(db, *, event, scope):
        calls.append({"db": db, "event": event, "scope": scope})
        return type("Request", (), {"schedule_error": None, "scheduled": True, "kick_required": False})()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_event_publication_service.persist_in_transaction_request",
        fake_persist,
    )
    service = CustomerBusinessObjectIntelligenceService()

    service.enqueue_change_refresh(
        object(),
        CustomerBusinessObjectChangeRefreshInput(
            team_id=2,
            customer_id=101,
            actor_id="9",
            source_type="invoice_application",
            source_id=701,
            change_type="deleted",
            object_name="INV-20260802-0001",
            payload={"invoice_amount": 50000},
        ),
    )

    assert calls[0]["event"].summary == "发票申请已删除: INV-20260802-0001"
    assert calls[0]["event"].payload == {
        "invoice_amount": 50000,
        "object_type": "invoice_application",
        "object_name": "INV-20260802-0001",
        "change_type": "deleted",
        "refresh_scope": "partial",
    }


def test_business_object_intelligence_service_labels_created_invoice_title(monkeypatch) -> None:
    calls = []

    def fake_persist(db, *, event, scope):
        calls.append({"db": db, "event": event, "scope": scope})
        return type("Request", (), {"schedule_error": None, "scheduled": True, "kick_required": False})()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_event_publication_service.persist_in_transaction_request",
        fake_persist,
    )
    service = CustomerBusinessObjectIntelligenceService()

    service.enqueue_change_refresh(
        object(),
        CustomerBusinessObjectChangeRefreshInput(
            team_id=2,
            customer_id=101,
            actor_id="9",
            source_type="invoice_title",
            source_id=801,
            change_type="created",
            object_name="越秀金融科技有限公司",
            payload={"is_default": True},
        ),
    )

    assert calls[0]["event"].summary == "开票抬头已新增: 越秀金融科技有限公司"


def test_business_object_intelligence_service_labels_updated_license_application(monkeypatch) -> None:
    calls = []

    def fake_persist(db, *, event, scope):
        calls.append({"db": db, "event": event, "scope": scope})
        return type("Request", (), {"schedule_error": None, "scheduled": True, "kick_required": False})()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_event_publication_service.persist_in_transaction_request",
        fake_persist,
    )
    service = CustomerBusinessObjectIntelligenceService()

    service.enqueue_change_refresh(
        object(),
        CustomerBusinessObjectChangeRefreshInput(
            team_id=2,
            customer_id=101,
            actor_id="9",
            source_type="license_application",
            source_id=1001,
            change_type="updated",
            object_name="LIC-202608-001",
            payload={},
        ),
    )

    assert calls[0]["event"].summary == "License申请已更新: LIC-202608-001"


def test_business_object_intelligence_service_labels_deleted_deployment_info(monkeypatch) -> None:
    calls = []

    def fake_persist(db, *, event, scope):
        calls.append({"db": db, "event": event, "scope": scope})
        return type("Request", (), {"schedule_error": None, "scheduled": True, "kick_required": False})()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_event_publication_service.persist_in_transaction_request",
        fake_persist,
    )
    service = CustomerBusinessObjectIntelligenceService()

    service.enqueue_change_refresh(
        object(),
        CustomerBusinessObjectChangeRefreshInput(
            team_id=2,
            customer_id=101,
            actor_id="9",
            source_type="deployment_info",
            source_id=901,
            change_type="deleted",
            object_name="生产环境",
            payload={},
        ),
    )

    assert calls[0]["event"].summary == "部署信息已删除: 生产环境"


def test_business_object_intelligence_service_derives_stable_source_version() -> None:
    service = CustomerBusinessObjectIntelligenceService()

    change = service.build_change(
        None,
        source_type="opportunity",
        business_object=type(
            "Opportunity",
            (),
            {
                "team_id": 2,
                "customer_id": 101,
                "id": 301,
                "opportunity_name": "大湾区气象项目",
                "version": 7,
                "last_modified_time": datetime(2026, 8, 29, 10, 30),
            },
        )(),
        change_type="updated",
        actor_id="9",
    )

    assert change is not None
    assert change.source_version == 7


def test_business_object_intelligence_service_supports_customer_master_data() -> None:
    service = CustomerBusinessObjectIntelligenceService()

    change = service.build_change(
        None,
        source_type="customer",
        business_object=type(
            "Customer",
            (),
            {
                "team_id": 2,
                "id": 101,
                "account_name": "广州市粤港澳大湾区气象智能装备研究中心",
                "industry": "政府",
                "city": "广州",
                "address": "天河区",
                "company_scale": "大型",
                "source": "线上注册",
                "status": 0,
                "owner_id": "9",
                "version": 4,
            },
        )(),
        change_type="updated",
        actor_id="9",
    )

    assert change is not None
    assert change.object_name == "广州市粤港澳大湾区气象智能装备研究中心"
    assert change.source_version == 4
    assert change.payload["industry"] == "政府"
    assert change.payload["owner_id"] == "9"


def test_business_object_intelligence_service_supports_customer_member_visibility_changes() -> None:
    service = CustomerBusinessObjectIntelligenceService()

    change = service.build_change(
        None,
        source_type="customer_member",
        business_object=type(
            "CustomerMember",
            (),
            {
                "team_id": 2,
                "id": 301,
                "customer_id": 101,
                "user_id": "9",
                "member_role": "PRESALES",
                "access_level": "FOLLOW_UP",
                "remark": "协同跟进",
                "is_active": True,
                "updated_time": datetime(2026, 8, 31, 10, 30),
                "post_commit_revision": 3,
            },
        )(),
        change_type="updated",
        actor_id="9",
    )

    assert change is not None
    assert change.object_name == "9"
    assert change.customer_id == 101
    assert change.source_version == 3
    assert change.payload == {
        "member_id": 301,
        "user_id": "9",
        "member_role": "PRESALES",
        "access_level": "FOLLOW_UP",
        "remark": "协同跟进",
        "is_active": True,
    }


def test_business_object_intelligence_service_preserves_summary_and_scope_after_commit(monkeypatch) -> None:
    calls = []

    def fake_enqueue(*, event, scope):
        calls.append({"event": event, "scope": scope})
        return type("Request", (), {"scheduled": False})()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_event_publication_service.enqueue_after_commit",
        fake_enqueue,
    )
    service = CustomerBusinessObjectIntelligenceService()
    change = CustomerBusinessObjectChangeRefreshInput(
        team_id=2,
        customer_id=101,
        actor_id="9",
        source_type="customer",
        source_id=101,
        change_type="created",
        object_name="客户A",
        source_version=3,
        summary="客户已创建，生成客户档案",
        scope="full",
    )

    service.enqueue_change_refresh_after_commit(change)

    assert calls[0]["scope"] == "full"
    assert calls[0]["event"].summary == "客户已创建，生成客户档案"
    assert calls[0]["event"].payload["refresh_scope"] == "full"


def test_business_object_intelligence_service_uses_one_canonical_trigger_mapping() -> None:
    service = CustomerBusinessObjectIntelligenceService()
    customer = type(
        "Customer",
        (),
        {
            "team_id": 2,
            "id": 101,
            "account_name": "客户A",
            "version": 1,
        },
    )()

    for change_type, expected_trigger in (
        ("created", "customer_business_object_created"),
        ("updated", "customer_business_object_updated"),
        ("deleted", "customer_business_object_deleted"),
    ):
        change = service.build_change(
            None,
            source_type="customer",
            business_object=customer,
            change_type=change_type,
            actor_id="9",
        )
        assert change is not None
        event = service._build_intelligence_event(change)
        assert event.trigger_type == expected_trigger


def test_business_object_intelligence_service_enqueues_customer_lifecycle_event_after_commit(monkeypatch) -> None:
    calls = []

    def fake_enqueue(*, event, scope):
        calls.append((event, scope))
        return type("Request", (), {"scheduled": False})()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_event_publication_service.enqueue_after_commit",
        fake_enqueue,
    )
    service = CustomerBusinessObjectIntelligenceService()
    customer = type(
        "Customer",
        (),
        {
            "team_id": 2,
            "id": 101,
            "version": 2,
        },
    )()

    service.enqueue_customer_lifecycle_refresh_after_commit(
        customer=customer,
        actor_id="9",
        trigger_type="customer_converted_from_lead",
        source_lead_id=77,
    )

    event, scope = calls[0]
    assert scope == "full"
    assert event.trigger_type == "customer_converted_from_lead"
    assert event.customer_id == 101
    assert event.source.source_type == "lead_conversion"
    assert event.source.source_object_id == "77"
    assert event.payload["refresh_scope"] == "full"
