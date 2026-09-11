from types import SimpleNamespace

import pytest

from app.api import customers as customers_api
from app.core.exceptions import ConflictException
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.schemas.customer import CustomerLifecycleStatusUpdate


def _customer(*, status: int, version: int = 4):
    return SimpleNamespace(
        id=21,
        public_id="cus_lifecycle",
        team_id=8,
        account_name="生命周期客户",
        status=status,
        version=version,
        owner_id="31",
    )


def _patch_route_dependencies(monkeypatch, customer):
    calls = SimpleNamespace(updates=[], logs=[], refreshes=[], notifications=[])
    monkeypatch.setattr(customers_api, "_get_editable_customer", lambda db, customer_id, team_id, user: customer)

    def update_status_with_version(db, db_customer, *, status, expected_version):
        calls.updates.append(
            {
                "customer": db_customer,
                "status": status,
                "expected_version": expected_version,
            }
        )
        db_customer.status = status
        db_customer.version += 1
        return db_customer

    monkeypatch.setattr(customers_api.customer_crud, "update_status_with_version", update_status_with_version)
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(
        customers_api,
        "_persist_customer_business_object_refresh_after_commit",
        lambda **kwargs: calls.refreshes.append(kwargs),
    )
    monkeypatch.setattr(
        customers_api.outbound_notification_job_service,
        "queue_committed",
        lambda *args, **kwargs: calls.notifications.append(kwargs),
    )
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)
    return calls


@pytest.mark.asyncio
async def test_lifecycle_status_following_to_won_updates_audits_refreshes_and_notifies(monkeypatch):
    customer = _customer(status=0)
    calls = _patch_route_dependencies(monkeypatch, customer)

    response = await customers_api.update_customer_lifecycle_status(
        customer_id=customer.public_id,
        status_update=CustomerLifecycleStatusUpdate(status=1, expected_version=4),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert response.status == 1
    assert response.version == 5
    assert calls.updates == [{"customer": customer, "status": 1, "expected_version": 4}]
    assert calls.logs[0]["event_type"] == customers_api.EventTypes.CUSTOMER_STATUS_CHANGED
    assert calls.logs[0]["content"] == {
        "previous_status": 0,
        "new_status": 1,
        "previous_version": 4,
        "new_version": 5,
    }
    assert calls.refreshes[0]["payload"] == {
        "change_type": "status_updated",
        "previous_status": 0,
        "new_status": 1,
    }
    assert calls.notifications[0]["event_type"] == OutboundNotificationEventType.ACCOUNT_STATUS_WON


@pytest.mark.asyncio
async def test_lifecycle_status_won_to_following_never_queues_lost_notification(monkeypatch):
    customer = _customer(status=1)
    calls = _patch_route_dependencies(monkeypatch, customer)

    response = await customers_api.update_customer_lifecycle_status(
        customer_id=customer.public_id,
        status_update=CustomerLifecycleStatusUpdate(status=0, expected_version=4),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert response.status == 0
    assert calls.notifications == []
    assert calls.refreshes[0]["payload"]["new_status"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("target_status", [2, 3])
async def test_lifecycle_status_maps_invalid_target_to_bad_request_without_mutation(monkeypatch, target_status):
    customer = _customer(status=0)
    calls = _patch_route_dependencies(monkeypatch, customer)

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer_lifecycle_status(
            customer_id=customer.public_id,
            status_update=SimpleNamespace(status=target_status, expected_version=4),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400
    assert customer.status == 0
    assert customer.version == 4
    assert calls.updates == []
    assert calls.logs == []
    assert calls.refreshes == []
    assert calls.notifications == []


@pytest.mark.asyncio
async def test_lifecycle_status_maps_stale_version_to_conflict_without_side_effects(monkeypatch):
    customer = _customer(status=0)
    calls = _patch_route_dependencies(monkeypatch, customer)

    def reject_stale(*args, **kwargs):
        raise ConflictException("客户已发生变化，请刷新后确认最新状态")

    monkeypatch.setattr(customers_api.customer_crud, "update_status_with_version", reject_stale)

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer_lifecycle_status(
            customer_id=customer.public_id,
            status_update=CustomerLifecycleStatusUpdate(status=1, expected_version=3),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 409
    assert customer.status == 0
    assert customer.version == 4
    assert calls.logs == []
    assert calls.refreshes == []
    assert calls.notifications == []
