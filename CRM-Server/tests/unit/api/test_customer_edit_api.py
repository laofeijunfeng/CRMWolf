from datetime import date
from types import SimpleNamespace

import pytest

from app.api import customers as customers_api
from app.core.exceptions import ConflictException
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.schemas.customer import CustomerLicenseSnapshotUpdate, CustomerLifecycleStatusUpdate, CustomerUpdate


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
    assert calls.logs[0]["operator_id"] == "9"
    assert calls.logs[0]["operator_name"] == "操作人"
    assert calls.logs[0]["team_id"] == customer.team_id
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


def _patch_snapshot_route_dependencies(monkeypatch, customer):
    calls = SimpleNamespace(updates=[], logs=[], refreshes=[])
    monkeypatch.setattr(customers_api, "_get_editable_customer", lambda db, customer_id, team_id, user: customer)

    def update_license_snapshot(db, db_customer, payload):
        calls.updates.append(payload)
        before = {
            "license_type": db_customer.license_type,
            "license_expiry_date": db_customer.license_expiry_date,
        }
        db_customer.license_type = payload.license_type
        db_customer.license_expiry_date = payload.license_expiry_date
        db_customer.version += 1
        after = {
            "license_type": db_customer.license_type,
            "license_expiry_date": db_customer.license_expiry_date,
        }
        return db_customer, before, after

    monkeypatch.setattr(customers_api.customer_crud, "update_license_snapshot", update_license_snapshot)
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(
        customers_api,
        "_persist_customer_business_object_refresh_after_commit",
        lambda **kwargs: calls.refreshes.append(kwargs),
    )
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)
    return calls


def _license_customer(*, version: int = 4):
    customer = _customer(status=0, version=version)
    customer.license_type = "TRIAL"
    customer.license_expiry_date = date(2026, 1, 1)
    return customer


@pytest.mark.asyncio
async def test_license_snapshot_updates_audit_and_refreshes(monkeypatch):
    customer = _license_customer()
    calls = _patch_snapshot_route_dependencies(monkeypatch, customer)

    response = await customers_api.update_customer_license_snapshot(
        customer_id=customer.public_id,
        snapshot_update=CustomerLicenseSnapshotUpdate(
            expected_version=4,
            license_type="OFFICIAL",
            license_expiry_date=date(2027, 1, 1),
        ),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert response.license_type == "OFFICIAL"
    assert response.license_expiry_date == date(2027, 1, 1)
    assert response.version == 5
    assert calls.logs[0]["event_type"] == customers_api.EventTypes.CUSTOMER_LICENSE_SNAPSHOT_UPDATED
    assert calls.logs[0]["operator_id"] == "9"
    assert calls.logs[0]["team_id"] == customer.team_id
    assert calls.logs[0]["content"] == {
        "before": {"license_type": "TRIAL", "license_expiry_date": "2026-01-01"},
        "after": {"license_type": "OFFICIAL", "license_expiry_date": "2027-01-01"},
        "changed_fields": ["license_type", "license_expiry_date"],
        "actor_id": "9",
        "team_id": customer.team_id,
    }
    assert calls.refreshes[0]["source_type"] == "customer"
    assert calls.refreshes[0]["summary"] == "客户授权汇总已更新，刷新客户智能档案"
    assert calls.refreshes[0]["payload"] == {
        "change_type": "license_snapshot_updated",
        "changed_fields": ["license_type", "license_expiry_date"],
    }


@pytest.mark.asyncio
async def test_license_snapshot_clear_normalizes_type_and_date(monkeypatch):
    customer = _license_customer()
    calls = _patch_snapshot_route_dependencies(monkeypatch, customer)

    payload = CustomerLicenseSnapshotUpdate(expected_version=4, license_type="OFFICIAL", license_expiry_date=None)
    await customers_api.update_customer_license_snapshot(
        customer_id=customer.public_id,
        snapshot_update=payload,
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert payload.license_type is None
    assert calls.updates[0].license_type is None
    assert calls.updates[0].license_expiry_date is None
    assert customer.license_type is None
    assert customer.license_expiry_date is None


@pytest.mark.asyncio
async def test_license_snapshot_maps_value_error_to_bad_request_without_side_effects(monkeypatch):
    customer = _license_customer()
    calls = _patch_snapshot_route_dependencies(monkeypatch, customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_license_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("授权快照无效")),
    )

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer_license_snapshot(
            customer_id=customer.public_id,
            snapshot_update=CustomerLicenseSnapshotUpdate(expected_version=4, license_type="TRIAL", license_expiry_date=date(2026, 1, 1)),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400
    assert calls.logs == []
    assert calls.refreshes == []


@pytest.mark.asyncio
async def test_license_snapshot_maps_stale_version_to_conflict_without_side_effects(monkeypatch):
    customer = _license_customer()
    calls = _patch_snapshot_route_dependencies(monkeypatch, customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_license_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConflictException("客户已发生变化，请刷新后确认最新状态")),
    )

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer_license_snapshot(
            customer_id=customer.public_id,
            snapshot_update=CustomerLicenseSnapshotUpdate(expected_version=3, license_type="TRIAL", license_expiry_date=date(2026, 1, 1)),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 409
    assert calls.logs == []
    assert calls.refreshes == []


@pytest.mark.asyncio
async def test_license_snapshot_permission_failure_has_no_mutation_or_side_effects(monkeypatch):
    customer = _license_customer()
    calls = SimpleNamespace(updates=[], logs=[], refreshes=[])
    monkeypatch.setattr(
        customers_api,
        "_get_editable_customer",
        lambda *args, **kwargs: (_ for _ in ()).throw(customers_api.HTTPException(status_code=403, detail="无权编辑客户")),
    )
    monkeypatch.setattr(customers_api.customer_crud, "update_license_snapshot", lambda *args, **kwargs: calls.updates.append(True))
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: calls.refreshes.append(kwargs))

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer_license_snapshot(
            customer_id=customer.public_id,
            snapshot_update=CustomerLicenseSnapshotUpdate(expected_version=4, license_type="TRIAL", license_expiry_date=date(2026, 1, 1)),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 403
    assert calls.updates == []
    assert calls.logs == []
    assert calls.refreshes == []
@pytest.mark.asyncio
async def test_lifecycle_status_permission_denial_has_no_mutation_or_side_effects(monkeypatch):
    customer = _customer(status=0)
    calls = SimpleNamespace(updates=[], logs=[], refreshes=[])
    monkeypatch.setattr(
        customers_api,
        "_get_editable_customer",
        lambda *args, **kwargs: (_ for _ in ()).throw(customers_api.HTTPException(status_code=403, detail="无权编辑客户")),
    )
    monkeypatch.setattr(customers_api.customer_crud, "update_status_with_version", lambda *args, **kwargs: calls.updates.append(True))
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: calls.refreshes.append(kwargs))

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.update_customer_lifecycle_status(
            customer_id=customer.public_id,
            status_update=CustomerLifecycleStatusUpdate(status=1, expected_version=4),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 403
    assert customer.status == 0
    assert customer.version == 4
    assert calls.updates == []
    assert calls.logs == []
    assert calls.refreshes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route_name", ["lifecycle", "snapshot"])
async def test_edit_routes_reject_customer_from_another_team(monkeypatch, route_name):
    customer = _license_customer()
    calls = SimpleNamespace(updates=[])

    def scoped_edit(db, customer_id, team_id, current_user):
        assert team_id == 7
        assert customer.team_id == 8
        raise customers_api.HTTPException(status_code=404, detail="客户不存在")

    monkeypatch.setattr(customers_api, "_get_editable_customer", scoped_edit)
    monkeypatch.setattr(customers_api.customer_crud, "update_status_with_version", lambda *args, **kwargs: calls.updates.append(True))
    monkeypatch.setattr(customers_api.customer_crud, "update_license_snapshot", lambda *args, **kwargs: calls.updates.append(True))

    with pytest.raises(customers_api.HTTPException) as exc_info:
        if route_name == "lifecycle":
            await customers_api.update_customer_lifecycle_status(
                customer_id=customer.public_id,
                status_update=CustomerLifecycleStatusUpdate(status=1, expected_version=4),
                team_id=7,
                current_user=SimpleNamespace(id=9, name="操作人"),
                db=SimpleNamespace(),
            )
        else:
            await customers_api.update_customer_license_snapshot(
                customer_id=customer.public_id,
                snapshot_update=CustomerLicenseSnapshotUpdate(expected_version=4, license_type="OFFICIAL"),
                team_id=7,
                current_user=SimpleNamespace(id=9, name="操作人"),
                db=SimpleNamespace(),
            )

    assert exc_info.value.status_code == 404
    assert calls.updates == []


@pytest.mark.asyncio
async def test_customer_put_emits_changed_values_and_partial_intelligence_refresh(monkeypatch):
    customer = _customer(status=0, version=4)
    customer.city = "北京"
    calls = SimpleNamespace(updates=[], logs=[], refreshes=[])
    monkeypatch.setattr(customers_api, "_get_editable_customer", lambda db, customer_id, team_id, user: customer)

    def update(db, db_customer, payload):
        calls.updates.append(payload)
        db_customer.city = payload.city
        db_customer.version += 1
        return db_customer

    monkeypatch.setattr(customers_api.customer_crud, "update", update)
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.refreshes.append(kwargs),
    )
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)

    response = customers_api.update_customer(
        customer_id=customer.public_id,
        customer_update=CustomerUpdate(city="上海", expected_version=4),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert response.city == "上海"
    assert response.version == 5
    assert calls.logs[0]["event_type"] == customers_api.EventTypes.CUSTOMER_UPDATED
    assert calls.logs[0]["operator_id"] == "9"
    assert calls.logs[0]["content"] == {
        "changed_fields": ["city"],
        "before": {"city": "北京"},
        "after": {"city": "上海"},
    }
    assert calls.refreshes[0]["change_type"] == "updated"
    assert calls.refreshes[0]["scope"] == "partial"
    assert calls.refreshes[0]["actor_id"] == "9"
    assert calls.refreshes[0]["payload"] == {"change_type": "updated", "changed_fields": ["city"]}
    assert len(calls.updates) == 1


@pytest.mark.asyncio
async def test_lifecycle_status_sends_canonical_intelligence_event_payload(monkeypatch):
    customer = _customer(status=0)
    calls = _patch_route_dependencies(monkeypatch, customer)
    calls.refreshes.clear()
    monkeypatch.setattr(
        customers_api,
        "_persist_customer_business_object_refresh_after_commit",
        lambda **kwargs: customers_api.customer_business_object_intelligence_service.enqueue_object_change_refresh_after_commit(**kwargs),
    )
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.refreshes.append(kwargs),
    )

    await customers_api.update_customer_lifecycle_status(
        customer_id=customer.public_id,
        status_update=CustomerLifecycleStatusUpdate(status=1, expected_version=4),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert calls.refreshes == [{
        "business_object": customer,
        "source_type": "customer",
        "summary": "客户状态已更新，刷新客户智能档案",
        "actor_id": "9",
        "payload": {"change_type": "status_updated", "previous_status": 0, "new_status": 1},
    }]


@pytest.mark.asyncio
async def test_license_snapshot_sends_canonical_intelligence_event_payload(monkeypatch):
    customer = _license_customer()
    calls = _patch_snapshot_route_dependencies(monkeypatch, customer)
    calls.refreshes.clear()
    monkeypatch.setattr(
        customers_api,
        "_persist_customer_business_object_refresh_after_commit",
        lambda **kwargs: customers_api.customer_business_object_intelligence_service.enqueue_object_change_refresh_after_commit(**kwargs),
    )
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: calls.refreshes.append(kwargs),
    )

    await customers_api.update_customer_license_snapshot(
        customer_id=customer.public_id,
        snapshot_update=CustomerLicenseSnapshotUpdate(
            expected_version=4,
            license_type="OFFICIAL",
            license_expiry_date=date(2027, 1, 1),
        ),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert calls.refreshes == [{
        "business_object": customer,
        "source_type": "customer",
        "summary": "客户授权汇总已更新，刷新客户智能档案",
        "actor_id": "9",
        "payload": {"change_type": "license_snapshot_updated", "changed_fields": ["license_type", "license_expiry_date"]},
    }]
