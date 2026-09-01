from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.api import customers as customers_api
from app.models.customer import Contact


def _contact(*, is_primary: int = 0) -> Contact:
    return Contact(
        id=601,
        team_id=2,
        customer_id=101,
        name="张总",
        gender=1,
        position="总经理",
        is_decision_maker=1,
        mobile="13800138000",
        is_primary=is_primary,
        created_time=datetime(2026, 8, 2, 12, 0, 0),
    )


@pytest.mark.asyncio
async def test_create_contact_triggers_customer_intelligence_refresh(monkeypatch):
    contact = _contact()
    scheduled = []

    monkeypatch.setattr(
        customers_api,
        "_get_editable_customer",
        lambda db, customer_id, team_id, current_user: SimpleNamespace(id=101, public_id="cus_101"),
    )
    monkeypatch.setattr(customers_api.contact_crud, "create", lambda db, obj_in, customer_id, team_id: contact)

    def fake_persist(**kwargs):
        scheduled.append(kwargs)
        return None

    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", fake_persist)

    result = await customers_api.create_contact(
        101,
        SimpleNamespace(),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.id == contact.id
    assert scheduled == [{
        "business_object": contact,
        "source_type": "customer_contact",
        "change_type": "created",
        "actor_id": "9",
    }]


@pytest.mark.asyncio
async def test_update_contact_triggers_customer_intelligence_refresh(monkeypatch):
    contact = _contact()
    scheduled = []

    monkeypatch.setattr(customers_api.contact_crud, "get_by_id", lambda db, contact_id, team_id: contact)
    monkeypatch.setattr(
        customers_api,
        "_get_editable_customer",
        lambda db, customer_id, team_id, current_user: SimpleNamespace(id=101, public_id="cus_101"),
    )
    monkeypatch.setattr(customers_api.contact_crud, "update", lambda db, db_obj, obj_in: contact)

    def fake_persist(**kwargs):
        scheduled.append(kwargs)
        return None

    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", fake_persist)

    result = await customers_api.update_contact(
        601,
        SimpleNamespace(),
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.id == contact.id
    assert scheduled == [{
        "business_object": contact,
        "source_type": "customer_contact",
        "change_type": "updated",
        "actor_id": "9",
    }]


@pytest.mark.asyncio
async def test_set_primary_contact_triggers_customer_intelligence_refresh(monkeypatch):
    contact = _contact(is_primary=1)
    scheduled = []

    monkeypatch.setattr(customers_api.contact_crud, "get_by_id", lambda db, contact_id, team_id: contact)
    monkeypatch.setattr(
        customers_api,
        "_get_editable_customer",
        lambda db, customer_id, team_id, current_user: SimpleNamespace(id=101, public_id="cus_101"),
    )
    monkeypatch.setattr(customers_api.contact_crud, "set_primary", lambda db, db_obj, team_id: contact)

    def fake_persist(**kwargs):
        scheduled.append(kwargs)
        return None

    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", fake_persist)

    result = await customers_api.set_primary_contact(
        601,
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.id == contact.id
    assert scheduled == [{
        "business_object": contact,
        "source_type": "customer_contact",
        "change_type": "updated",
        "actor_id": "9",
    }]


@pytest.mark.asyncio
async def test_delete_contact_triggers_customer_intelligence_refresh_after_success(monkeypatch):
    contact = _contact()
    scheduled = []

    monkeypatch.setattr(customers_api.contact_crud, "get_by_id", lambda db, contact_id, team_id: contact)
    monkeypatch.setattr(
        customers_api,
        "_get_editable_customer",
        lambda db, customer_id, team_id, current_user: SimpleNamespace(id=101, public_id="cus_101"),
    )
    monkeypatch.setattr(customers_api.contact_crud, "delete", lambda db, db_obj: contact)

    def fake_persist(**kwargs):
        scheduled.append(kwargs)
        return None

    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", fake_persist)

    result = await customers_api.delete_contact(
        601,
        team_id=2,
        current_user=SimpleNamespace(id=9),
        db=object(),
    )

    assert result.message == "删除成功"
    assert scheduled == [{
        "business_object": contact,
        "source_type": "customer_contact",
        "change_type": "deleted",
        "actor_id": "9",
    }]


@pytest.mark.asyncio
async def test_delete_contact_does_not_trigger_customer_intelligence_refresh_when_delete_fails(monkeypatch):
    contact = _contact(is_primary=1)
    scheduled = []

    def fake_delete(db, db_obj):
        raise ValueError("不能删除主联系人")

    monkeypatch.setattr(customers_api.contact_crud, "get_by_id", lambda db, contact_id, team_id: contact)
    monkeypatch.setattr(
        customers_api,
        "_get_editable_customer",
        lambda db, customer_id, team_id, current_user: SimpleNamespace(id=101, public_id="cus_101"),
    )
    monkeypatch.setattr(customers_api.contact_crud, "delete", fake_delete)
    monkeypatch.setattr(
        customers_api,
        "_persist_customer_business_object_refresh_after_commit",
        lambda **kwargs: scheduled.append(kwargs),
    )

    with pytest.raises(customers_api.HTTPException):
        await customers_api.delete_contact(
            601,
            team_id=2,
            current_user=SimpleNamespace(id=9),
            db=object(),
        )

    assert scheduled == []
