from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import customers as customers_api


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
