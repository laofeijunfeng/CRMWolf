from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api import customers as customers_api
from app.core import deps
from app.core.exceptions import ConflictException
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.crud.customer import contact_crud, customer_crud
from app.schemas.customer import (
    ContactCreate,
    CustomerCreate,
    CustomerLicenseSnapshotUpdate,
    CustomerLifecycleStatusUpdate,
    CustomerUpdate,
)


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
    real_plan_update = customers_api.customer_crud.plan_and_update_status_with_version
    crud_db = MagicMock()
    crud_db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value = customer

    def plan_and_update_status_with_version(db, db_customer, *, target_status, expected_version, planner):
        result = real_plan_update(
            crud_db,
            db_customer,
            target_status=target_status,
            expected_version=expected_version,
            planner=planner,
        )
        calls.updates.append({"customer": db_customer, "status": target_status, "expected_version": expected_version})
        return result

    monkeypatch.setattr(customers_api.customer_crud, "plan_and_update_status_with_version", plan_and_update_status_with_version)
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

    monkeypatch.setattr(customers_api.customer_crud, "plan_and_update_status_with_version", reject_stale)

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
    crud_db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value = customer

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
        "previous_version": 4,
        "new_version": 5,
        "actor_id": "9",
        "team_id": customer.team_id,
    }
@pytest.mark.asyncio
async def test_license_snapshot_audit_uses_persisted_version_not_expected_version(monkeypatch):
    customer = _license_customer(version=8)
    calls = _patch_snapshot_route_dependencies(monkeypatch, customer)
    before = {"license_type": "TRIAL", "license_expiry_date": date(2026, 1, 1)}
    after = {"license_type": "OFFICIAL", "license_expiry_date": date(2027, 1, 1)}
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_license_snapshot",
        lambda db, db_customer, payload: (customer, before, after),
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

    assert calls.logs[0]["content"]["previous_version"] == 7
    assert calls.logs[0]["content"]["new_version"] == 8


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
    def update_with_audit(db, db_customer, payload):
        calls.updates.append(payload)
        setattr(db_customer, "city", payload.city)
        db_customer.version += 1
        return db_customer, {"city": "北京"}, {"city": payload.city}

    monkeypatch.setattr(customers_api.customer_crud, "update_with_audit", update_with_audit)

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
async def test_customer_put_maps_stale_version_to_conflict_without_side_effects(monkeypatch):
    customer = _customer(status=0)
    customer.city = "北京"
    calls = SimpleNamespace(logs=[], refreshes=[])
    _allow_edit_permission(monkeypatch, customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConflictException("客户已发生变化，请刷新后确认最新状态")),
    )

    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: calls.refreshes.append(kwargs))

    with pytest.raises(customers_api.HTTPException) as exc_info:
        customers_api.update_customer(
            customer_id=customer.public_id,
            customer_update=CustomerUpdate(city="上海", expected_version=4),
            team_id=customer.team_id,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=MagicMock(),
        )

    assert exc_info.value.status_code == 409
    assert customer.city == "北京"
    assert calls.logs == []
    assert calls.refreshes == []


@pytest.mark.asyncio
async def test_customer_put_updates_profile_status_industry_and_license_once(monkeypatch):
    customer = _customer(status=0, version=4)
    customer.city = "北京"
    customer.industry = "internet_saas"
    customer.license_type = "TRIAL"
    customer.license_expiry_date = date(2026, 1, 1)
    calls = SimpleNamespace(logs=[], refreshes=[], notifications=[])
    _allow_edit_permission(monkeypatch, customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda db, db_customer, payload: (
            setattr(db_customer, "city", "上海") or
            setattr(db_customer, "status", 1) or
            setattr(db_customer, "industry", "finance_securities") or
            setattr(db_customer, "license_type", "OFFICIAL") or
            setattr(db_customer, "license_expiry_date", date(2027, 1, 1)) or
            setattr(db_customer, "version", 5) or
            (db_customer,
             {"city": "北京", "status": 0, "industry": "internet_saas", "license_type": "TRIAL", "license_expiry_date": date(2026, 1, 1)},
             {"city": "上海", "status": 1, "industry": "finance_securities", "license_type": "OFFICIAL", "license_expiry_date": date(2027, 1, 1)})
        ),
    )
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: calls.logs.append(kwargs))
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: calls.refreshes.append(kwargs))
    monkeypatch.setattr(customers_api.outbound_notification_job_service, "queue_committed", lambda *args, **kwargs: calls.notifications.append(kwargs))
    monkeypatch.setattr(customers_api, "_customer_response", lambda db_session, value: value)

    response = customers_api.update_customer(
        customer.public_id,
        CustomerUpdate(
            expected_version=4,
            city="上海",
            status=1,
            industry="finance_securities",
            license_type="OFFICIAL",
            license_expiry_date=date(2027, 1, 1),
        ),
        team_id=customer.team_id,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=MagicMock(),
    )

    assert response.version == 5
    assert calls.logs[0]["event_type"] == customers_api.EventTypes.CUSTOMER_UPDATED
    assert calls.logs[0]["content"] == {
        "changed_fields": ["city", "status", "industry", "license_type", "license_expiry_date"],
        "before": {
            "city": "北京",
            "status": 0,
            "industry": "internet_saas",
            "license_type": "TRIAL",
            "license_expiry_date": "2026-01-01",
        },
        "after": {
            "city": "上海",
            "status": 1,
            "industry": "finance_securities",
            "license_type": "OFFICIAL",
            "license_expiry_date": "2027-01-01",
        },
    }
    assert calls.refreshes[0]["scope"] == "partial"
    assert calls.notifications == []



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
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda db, obj, payload: (
            setattr(obj, "source_id", 12)
            or setattr(obj, "source", "新来源")
            or (obj, {"source_public_id": "src_old"}, {"source_public_id": "src_new"})
        ),
    )

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
        "changed_fields": ["source_public_id"],
        "before": {"source_public_id": "src_old"},
        "after": {"source_public_id": "src_new"},
    }

    assert "source_id" not in calls.logs[0]["content"]["before"]
    assert "source_id" not in calls.logs[0]["content"]["after"]


def _created_customer() -> SimpleNamespace:
    return SimpleNamespace(
        id=31,
        public_id="cus_created",
        team_id=8,
        account_name="新客户",
        city="上海",
        industry="internet_saas",
        status=1,
        license_type="TRIAL",
        license_expiry_date=date(2026, 12, 31),
        owner_id="9",
        version=1,
    )


@pytest.mark.asyncio
async def test_create_customer_commits_customer_and_contact_as_one_transaction(monkeypatch):
    customer = _created_customer()
    calls = SimpleNamespace(customer=[], contact=[], refreshes=[], notifications=[])
    db = MagicMock()

    def create_customer(**kwargs):
        calls.customer.append(kwargs)
        return customer

    def create_contact(**kwargs):
        calls.contact.append(kwargs)
        return SimpleNamespace(id=41, name="李华")

    _allow_edit_permission(monkeypatch, customer)
    monkeypatch.setattr(customers_api.customer_crud, "get_by_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(customers_api.lead_crud, "get_by_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(customers_api.customer_crud, "create", create_customer)
    monkeypatch.setattr(customers_api.contact_crud, "create", create_contact)
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
    monkeypatch.setattr(customers_api, "_customer_response", lambda db_session, value: value)

    response = await customers_api.create_customer(
        CustomerCreate(
            account_name="新客户",
            city="上海",
            industry="internet_saas",
            status=1,
            license_type="TRIAL",
            license_expiry_date=date(2026, 12, 31),
            primary_contact={
                "name": "李华",
                "mobile": "13800138000",
                "position": "CTO",
                "gender": "1",
                "is_decision_maker": False,
            },
        ),
        team_id=8,
        current_user=SimpleNamespace(id=9, name="操作人"),
        db=db,
    )

    assert response is customer
    assert calls.customer[0]["commit"] is False
    assert calls.contact[0]["commit"] is False
    assert calls.customer[0]["obj_in"].status == 1
    assert calls.customer[0]["obj_in"].license_type == "TRIAL"
    db.commit.assert_called_once()
    assert calls.notifications == []
    assert calls.refreshes[0]["scope"] == "full"


@pytest.mark.asyncio
async def test_create_customer_rolls_back_when_contact_write_fails(monkeypatch):
    customer = _created_customer()
    db = MagicMock()
    monkeypatch.setattr(customers_api.customer_crud, "get_by_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(customers_api.lead_crud, "get_by_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(customers_api.customer_crud, "create", lambda **kwargs: customer)
    monkeypatch.setattr(
        customers_api.contact_crud,
        "create",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("联系人写入失败")),
    )
    monkeypatch.setattr(
        customers_api.customer_business_object_intelligence_service,
        "enqueue_object_change_refresh_after_commit",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("失败事务不能刷新客户档案")),
    )

    with pytest.raises(customers_api.HTTPException) as exc_info:
        await customers_api.create_customer(
            CustomerCreate(
                account_name="不会留下半成品",
                city="上海",
                primary_contact={
                    "name": "李华",
                    "mobile": "13800138000",
                    "position": "CTO",
                    "gender": "1",
                    "is_decision_maker": False,
                },
            ),
            team_id=8,
            current_user=SimpleNamespace(id=9, name="操作人"),
            db=db,
        )

    assert exc_info.value.status_code == 400
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def _patch_create_dependencies(monkeypatch, *, industry=None, industries=None, logs=None):
    monkeypatch.setattr(
        "app.crud.customer.resolve_source_for_entity_write",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.crud.customer.industry_crud.get_by_code",
        lambda db, code: industry if industry is not None and getattr(industry, "code", None) == code else None,
    )
    monkeypatch.setattr(
        "app.crud.customer.industry_crud.get_all_active",
        lambda db: industries or [],
    )
    monkeypatch.setattr(
        "app.services.operation_log_service.operation_log_service.log",
        lambda **kwargs: (logs.append(kwargs) if logs is not None else None),
    )


def test_create_persists_status_license_and_industry_code(monkeypatch):
    db = MagicMock()
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    _patch_create_dependencies(
        monkeypatch,
        industry=SimpleNamespace(code="internet_saas", name="互联网SaaS", is_active=1),
    )

    customer_crud.create(
        db,
        CustomerCreate(
            account_name="新客户",
            city="上海",
            industry="internet_saas",
            status=1,
            license_type="TRIAL",
            license_expiry_date=date(2026, 12, 31),
        ),
        creator_id="9",
        team_id=8,
        operator_name="操作人",
    )

    created = added[0]
    assert created.status == 1
    assert created.license_type == "TRIAL"
    assert created.license_expiry_date == date(2026, 12, 31)
    assert created.industry == "internet_saas"
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(created)
    db.flush.assert_not_called()


def test_create_stores_code_for_exact_active_industry_name(monkeypatch):
    db = MagicMock()
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    _patch_create_dependencies(
        monkeypatch,
        industries=[SimpleNamespace(code="internet_saas", name="互联网", is_active=1)],
    )

    customer_crud.create(
        db,
        CustomerCreate(account_name="新客户", city="上海", industry="互联网"),
        creator_id="9",
        team_id=8,
    )

    assert added[0].industry == "internet_saas"


@pytest.mark.parametrize(
    "industry,lookup",
    [
        ("missing", {"industry": None, "industries": []}),
        (
            "互联网",
            {
                "industry": None,
                "industries": [
                    SimpleNamespace(code="internet_saas", name="互联网", is_active=1),
                    SimpleNamespace(code="internet_media", name="互联网", is_active=1),
                ],
            },
        ),
        (
            "legacy",
            {"industry": SimpleNamespace(code="legacy", name="旧行业", is_active=0), "industries": []},
        ),
    ],
)
def test_create_rejects_missing_ambiguous_and_inactive_industry(monkeypatch, industry, lookup):
    db = MagicMock()
    _patch_create_dependencies(
        monkeypatch,
        industry=lookup["industry"],
        industries=lookup["industries"],
    )

    with pytest.raises(ValueError, match="行业代码不存在或已停用"):
        customer_crud.create(
            db,
            CustomerCreate(account_name="新客户", city="上海", industry=industry),
            creator_id="9",
            team_id=8,
        )

    db.commit.assert_not_called()


def test_create_flushes_without_commit_or_refresh_when_commit_false(monkeypatch):
    db = MagicMock()
    added = []
    logs = []
    db.add.side_effect = lambda obj: added.append(obj)
    _patch_create_dependencies(monkeypatch, logs=logs)

    created = customer_crud.create(
        db,
        CustomerCreate(account_name="新客户", city="上海"),
        creator_id="9",
        team_id=8,
        commit=False,
    )

    assert created is added[0]
    db.flush.assert_called_once()
    db.commit.assert_not_called()
    db.refresh.assert_not_called()
    assert logs[0]["commit"] is False


def test_contact_create_flushes_without_commit_or_refresh_when_commit_false(monkeypatch):
    db = MagicMock()
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    monkeypatch.setattr(contact_crud, "get_primary_by_customer_id", lambda *args, **kwargs: None)

    created = contact_crud.create(
        db,
        ContactCreate(
            name="李华",
            mobile="13800138000",
            position="CTO",
            gender="1",
            is_decision_maker=False,
        ),
        customer_id=31,
        team_id=8,
        is_primary=True,
        commit=False,
    )

    assert created is added[0]
    db.flush.assert_called_once()
    db.commit.assert_not_called()
    db.refresh.assert_not_called()
