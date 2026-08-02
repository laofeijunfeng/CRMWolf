from __future__ import annotations

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
        "customer_intelligence_refresh_service.trigger_business_object_change_refresh",
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

    assert calls[0]["summary"] == "回款计划已更新: 首付款"
    assert calls[0]["payload"] == {
        "planned_amount": 50000,
        "object_type": "payment_plan",
        "object_name": "首付款",
        "change_type": "updated",
    }
    assert "501" not in calls[0]["summary"]


def test_business_object_intelligence_service_enqueues_sync_refresh(monkeypatch) -> None:
    calls = []

    def fake_enqueue(db, **kwargs):
        calls.append({"db": db, **kwargs})
        return object()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_refresh_service.enqueue_business_object_change_refresh",
        fake_enqueue,
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

    assert calls[0]["summary"] == "发票申请已删除: INV-20260802-0001"
    assert calls[0]["payload"] == {
        "invoice_amount": 50000,
        "object_type": "invoice_application",
        "object_name": "INV-20260802-0001",
        "change_type": "deleted",
    }


def test_business_object_intelligence_service_labels_created_invoice_title(monkeypatch) -> None:
    calls = []

    def fake_enqueue(db, **kwargs):
        calls.append({"db": db, **kwargs})
        return object()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_refresh_service.enqueue_business_object_change_refresh",
        fake_enqueue,
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

    assert calls[0]["summary"] == "开票抬头已新增: 越秀金融科技有限公司"


def test_business_object_intelligence_service_labels_updated_license_application(monkeypatch) -> None:
    calls = []

    def fake_enqueue(db, **kwargs):
        calls.append({"db": db, **kwargs})
        return object()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_refresh_service.enqueue_business_object_change_refresh",
        fake_enqueue,
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

    assert calls[0]["summary"] == "License申请已更新: LIC-202608-001"


def test_business_object_intelligence_service_labels_deleted_deployment_info(monkeypatch) -> None:
    calls = []

    def fake_enqueue(db, **kwargs):
        calls.append({"db": db, **kwargs})
        return object()

    monkeypatch.setattr(
        "app.services.customer_business_object_intelligence_service."
        "customer_intelligence_refresh_service.enqueue_business_object_change_refresh",
        fake_enqueue,
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

    assert calls[0]["summary"] == "部署信息已删除: 生产环境"
