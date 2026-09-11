import pytest
from pydantic import ValidationError

from app.schemas.customer import CustomerUpdate


def test_customer_update_carries_expected_version_for_optimistic_locking() -> None:
    payload = CustomerUpdate(account_name="新客户名称", expected_version=7)

    assert payload.expected_version == 7


def test_customer_update_rejects_invalid_expected_version() -> None:
    with pytest.raises(ValidationError):
        CustomerUpdate(expected_version=0)

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.exceptions import ConflictException
from app.crud.customer import customer_crud


def test_customer_update_rejects_a_stale_version_before_mutating() -> None:
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, city="北京")
    locked_query = db.query.return_value.filter.return_value.with_for_update.return_value
    locked_query.first.return_value = current

    with pytest.raises(ConflictException, match="已发生变化"):
        customer_crud.update(db, current, CustomerUpdate(city="上海", expected_version=3))

    assert current.city == "北京"
    db.commit.assert_not_called()


def test_customer_update_locks_and_updates_when_version_matches() -> None:
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, city="北京")
    locked_query = db.query.return_value.filter.return_value.with_for_update.return_value
    locked_query.first.return_value = current

    updated = customer_crud.update(db, current, CustomerUpdate(city="上海", expected_version=4))

    assert updated is current
    assert current.city == "上海"
    assert current.version == 5
    db.commit.assert_called_once()

def test_update_customer_logs_only_changed_fields(monkeypatch) -> None:
    from app.api import customers as customers_api

    customer = SimpleNamespace(
        id=1,
        public_id="cus_1",
        team_id=9,
        account_name="旧客户",
        city="北京",
        industry="old",
        version=4,
    )
    user = SimpleNamespace(id=7, name="操作人")
    logged = []
    monkeypatch.setattr(customers_api, "_get_editable_customer", lambda *args: customer)
    monkeypatch.setattr(customers_api, "_ensure_customer_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(customers_api.customer_crud, "update", lambda db, current, payload: setattr(current, "city", payload.city) or current)
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: None)
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: logged.append(kwargs))

    result = customers_api.update_customer(
        "cus_1",
        CustomerUpdate(city="上海", expected_version=4),
        team_id=9,
        current_user=user,
        db=MagicMock(),
    )

    assert result is customer
    assert logged[0]["event_type"] == "CUSTOMER_UPDATED"
    assert logged[0]["event_action"] == "UPDATE"
    assert logged[0]["resource_type"] == "CUSTOMER"
    assert logged[0]["team_id"] == 9
    assert logged[0]["operator_id"] == "7"
    assert logged[0]["content"] == {
        "changed_fields": ["city"],
        "before": {"city": "北京"},
        "after": {"city": "上海"},
    }
