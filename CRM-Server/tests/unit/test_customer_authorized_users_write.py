from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.crud.customer import customer_crud
from app.schemas.customer import CustomerUpdate


def _customer(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": 1,
        "team_id": 9,
        "version": 4,
        "account_name": "测试客户",
        "city": "北京",
        "address": None,
        "company_scale": "1-50人",
        "default_procurement_method_id": None,
        "source_id": None,
        "source": None,
        "industry": "internet_saas",
        "status": 0,
        "license_type": "TRIAL",
        "license_expiry_date": date(2026, 1, 1),
        "license_authorized_users": 20,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _db_for(customer: SimpleNamespace) -> MagicMock:
    db = MagicMock()
    locked = (
        db.query.return_value.options.return_value.filter.return_value
        .populate_existing.return_value.with_for_update.return_value
    )
    locked.first.return_value = customer
    return db


def test_update_writes_authorized_users_without_touching_license_pair() -> None:
    customer = _customer()
    db = _db_for(customer)

    updated, before, after = customer_crud.update_with_audit(
        db,
        customer,
        CustomerUpdate(expected_version=4, license_authorized_users=80),
    )

    assert updated is customer
    assert customer.license_authorized_users == 80
    assert customer.license_type == "TRIAL"
    assert customer.license_expiry_date == date(2026, 1, 1)
    assert before == {"license_authorized_users": 20}
    assert after == {"license_authorized_users": 80}
    assert customer.version == 5


def test_update_keeps_authorized_users_when_only_expiry_changes() -> None:
    customer = _customer()
    db = _db_for(customer)

    customer_crud.update_with_audit(
        db,
        customer,
        CustomerUpdate(expected_version=4, license_expiry_date=date(2027, 1, 1)),
    )

    assert customer.license_authorized_users == 20
    assert customer.license_type == "TRIAL"
    assert customer.license_expiry_date == date(2027, 1, 1)


def test_clearing_expiry_does_not_clear_authorized_users() -> None:
    customer = _customer()
    db = _db_for(customer)

    customer_crud.update_with_audit(
        db,
        customer,
        CustomerUpdate(expected_version=4, license_expiry_date=None),
    )

    assert customer.license_type is None
    assert customer.license_expiry_date is None
    assert customer.license_authorized_users == 20


def test_update_clears_authorized_users_when_null_is_sent() -> None:
    customer = _customer()
    db = _db_for(customer)

    _updated, before, after = customer_crud.update_with_audit(
        db,
        customer,
        CustomerUpdate(expected_version=4, license_authorized_users=None),
    )

    assert customer.license_authorized_users is None
    assert customer.license_type == "TRIAL"
    assert customer.license_expiry_date == date(2026, 1, 1)
    assert before == {"license_authorized_users": 20}
    assert after == {"license_authorized_users": None}
