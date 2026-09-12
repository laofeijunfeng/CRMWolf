from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api import customers as customers_api
from app.core import deps
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
        source_id=11,
        source="旧来源",
    )


def _allow_edit_permission(monkeypatch, customer):
    monkeypatch.setattr(
        customers_api.customer_crud,
        "get_by_public_id",
        lambda db, public_id, team_id: customer if public_id == customer.public_id and team_id == customer.team_id else None,
    )
    monkeypatch.setattr(
        deps.permission_crud,
        "get_user_permissions",
        lambda db, user_id, team_id: [SimpleNamespace(code="customer:edit:all")],
    )
    monkeypatch.setattr(deps, "_customer_member_has_access", lambda *args, **kwargs: False)


def _deny_edit_permission(monkeypatch, customer):
    monkeypatch.setattr(
        customers_api.customer_crud,
        "get_by_public_id",
        lambda db, public_id, team_id: customer if public_id == customer.public_id and team_id == customer.team_id else None,
    )
    monkeypatch.setattr(deps.permission_crud, "get_user_permissions", lambda db, user_id, team_id: [])
    monkeypatch.setattr(deps, "_customer_member_has_access", lambda *args, **kwargs: False)


def _patch_route_dependencies(monkeypatch, customer):
    calls = SimpleNamespace(updates=[], logs=[], refreshes=[], notifications=[])
    _allow_edit_permission(monkeypatch, customer)
    real_update_status = customers_api.customer_crud.update_status_with_version
    crud_db = MagicMock()
    crud_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = customer

    def update_status_with_version(db, db_customer, *, status, expected_version):
        calls.updates.append({"customer": db_customer, "status": status, "expected_version": expected_version})
        return real_update_status(crud_db, db_customer, status=status, expected_version=expected_version)

    monkeypatch.setattr(customers_api.customer_crud, "update_status_with_version", update_status_with_version)
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
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


def _patch_snapshot_route_dependencies(monkeypatch, customer):
    calls = SimpleNamespace(updates=[], logs=[], refreshes=[])
    _allow_edit_permission(monkeypatch, customer)
    real_update_snapshot = customers_api.customer_crud.update_license_snapshot
    crud_db = MagicMock()
    crud_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = customer

    def update_license_snapshot(db, db_customer, payload):
        calls.updates.append(payload)
        return real_update_snapshot(crud_db, db_customer, payload)

    monkeypatch.setattr(customers_api.customer_crud, "update_license_snapshot", update_license_snapshot)
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
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
    _deny_edit_permission(monkeypatch, customer)
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
    _deny_edit_permission(monkeypatch, customer)
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

    _allow_edit_permission(monkeypatch, customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "get_by_public_id",
        lambda db, customer_id, team_id: None if team_id == 7 else customer,
    )
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
    _allow_edit_permission(monkeypatch, customer)
    real_update = customers_api.customer_crud.update
    crud_db = MagicMock()
    crud_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = customer

    def update(db, db_customer, payload):
        calls.updates.append(payload)
        return real_update(crud_db, db_customer, payload)

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

    await customers_api.update_customer_lifecycle_status(
        customer_id=customer.public_id,
        status_update=CustomerLifecycleStatusUpdate(status=1, expected_version=4),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert calls.refreshes == [{
        "source_type": "customer",
        "business_object": customer,
        "change_type": "updated",
        "actor_id": "9",
        "summary": "客户状态已更新，刷新客户智能档案",
        "payload": {"change_type": "status_updated", "previous_status": 0, "new_status": 1},
        "scope": "partial",
    }]


@pytest.mark.asyncio
async def test_license_snapshot_sends_canonical_intelligence_event_payload(monkeypatch):
    customer = _license_customer()
    calls = _patch_snapshot_route_dependencies(monkeypatch, customer)
    calls.refreshes.clear()

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
        "source_type": "customer",
        "business_object": customer,
        "change_type": "updated",
        "actor_id": "9",
        "summary": "客户授权汇总已更新，刷新客户智能档案",
        "payload": {"change_type": "license_snapshot_updated", "changed_fields": ["license_type", "license_expiry_date"]},
        "scope": "partial",
    }]


def test_customer_put_source_audit_uses_public_ids_without_internal_ids(monkeypatch):
    customer = _customer(status=0, version=4)
    calls = SimpleNamespace(logs=[], refreshes=[])
    _allow_edit_permission(monkeypatch, customer)
    old_source = SimpleNamespace(id=11, public_id="src_old", name="旧来源")
    new_source = SimpleNamespace(id=12, public_id="src_new", name="新来源")
    monkeypatch.setattr(customers_api, "get_by_id", lambda db, source_id, team_id: old_source if source_id == 11 else new_source)
    monkeypatch.setattr(
        "app.crud.customer.resolve_source_for_entity_write",
        lambda db, team_id, **kwargs: new_source,
    )
    real_update = customers_api.customer_crud.update
    crud_db = MagicMock()
    crud_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = customer

    monkeypatch.setattr(customers_api.customer_crud, "update", lambda db, obj, payload: real_update(crud_db, obj, payload))
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: calls.refreshes.append(kwargs))
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)

    response = customers_api.update_customer(
        customer_id=customer.public_id,
        customer_update=CustomerUpdate(source="新来源", source_public_id="src_new", expected_version=4),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=SimpleNamespace(),
    )

    assert response.source_id == 12
    assert calls.logs[0]["content"] == {
        "changed_fields": ["source", "source_public_id"],
        "before": {"source": "旧来源", "source_public_id": "src_old"},
        "after": {"source": "新来源", "source_public_id": "src_new"},
    }
    assert "source_id" not in calls.logs[0]["content"]["before"]
    assert "source_id" not in calls.logs[0]["content"]["after"]
