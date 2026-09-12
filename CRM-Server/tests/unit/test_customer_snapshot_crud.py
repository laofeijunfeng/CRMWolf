from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ConflictException
from app.crud.customer import customer_crud
from app.schemas.customer import CustomerLicenseSnapshotUpdate, CustomerUpdate


def _locked_customer(db, customer):
    locked_query = db.query.return_value.filter.return_value.with_for_update.return_value
    locked_query.first.return_value = customer
    return locked_query


def test_update_license_snapshot_updates_pair_and_increments_version_once():
    db = MagicMock()
    customer = SimpleNamespace(
        id=1,
        team_id=9,
        version=4,
        license_type="TRIAL",
        license_expiry_date=date(2026, 1, 1),
    )
    _locked_customer(db, customer)
    payload = CustomerLicenseSnapshotUpdate(
        expected_version=4,
        license_type="OFFICIAL",
        license_expiry_date=date(2027, 1, 1),
    )

    updated, before, after = customer_crud.update_license_snapshot(db, customer, payload)

    assert updated is customer
    assert before == {"license_type": "TRIAL", "license_expiry_date": date(2026, 1, 1)}
    assert after == {"license_type": "OFFICIAL", "license_expiry_date": date(2027, 1, 1)}
    assert customer.license_type == "OFFICIAL"
    assert customer.license_expiry_date == date(2027, 1, 1)
    assert customer.version == 5
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(customer)


def test_update_license_snapshot_rejects_stale_version_before_mutation():
    db = MagicMock()
    customer = SimpleNamespace(
        id=1,
        team_id=9,
        version=4,
        license_type="TRIAL",
        license_expiry_date=date(2026, 1, 1),
    )
    _locked_customer(db, customer)
    payload = CustomerLicenseSnapshotUpdate(
        expected_version=3,
        license_type="OFFICIAL",
        license_expiry_date=date(2027, 1, 1),
    )

    with pytest.raises(ConflictException, match="已发生变化"):
        customer_crud.update_license_snapshot(db, customer, payload)

    assert customer.license_type == "TRIAL"
    assert customer.license_expiry_date == date(2026, 1, 1)
    assert customer.version == 4
    db.commit.assert_not_called()


def test_update_license_snapshot_clears_type_when_expiry_is_none():
    db = MagicMock()
    customer = SimpleNamespace(
        id=1,
        team_id=9,
        version=4,
        license_type="OFFICIAL",
        license_expiry_date=date(2027, 1, 1),
    )
    _locked_customer(db, customer)
    payload = CustomerLicenseSnapshotUpdate(expected_version=4, license_expiry_date=None)

    _, before, after = customer_crud.update_license_snapshot(db, customer, payload)

    assert before == {"license_type": "OFFICIAL", "license_expiry_date": date(2027, 1, 1)}
    assert after == {"license_type": None, "license_expiry_date": None}
    assert customer.license_type is None
    assert customer.license_expiry_date is None


def test_customer_update_rejects_unknown_industry_before_mutation(monkeypatch):
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, industry="old", city="北京")
    locked_query = db.query.return_value.filter.return_value.with_for_update.return_value
    locked_query.first.return_value = current
    monkeypatch.setattr(
        "app.crud.industry.industry_crud.get_by_code_with_parent",
        lambda db, code: None,
    )

    with pytest.raises(ValueError, match="行业"):
        customer_crud.update(db, current, CustomerUpdate(industry="missing", expected_version=4))

    assert current.industry == "old"
    db.commit.assert_not_called()


def test_customer_update_retains_current_inactive_industry_code(monkeypatch):
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, industry="legacy", city="北京")
    locked_query = db.query.return_value.filter.return_value.with_for_update.return_value
    locked_query.first.return_value = current
    monkeypatch.setattr(
        "app.crud.industry.industry_crud.get_by_code_with_parent",
        lambda db, code: SimpleNamespace(code=code, is_active=0),
    )

    updated = customer_crud.update(
        db,
        current,
        CustomerUpdate(industry="legacy", expected_version=4),
    )

    assert updated is current
    assert current.industry == "legacy"
    assert current.version == 5
    db.commit.assert_called_once()


def test_customer_update_accepts_active_industry_code(monkeypatch):
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, industry="old", city="北京")
    locked_query = db.query.return_value.filter.return_value.with_for_update.return_value
    locked_query.first.return_value = current
    monkeypatch.setattr(
        "app.crud.industry.industry_crud.get_by_code_with_parent",
        lambda db, code: SimpleNamespace(code=code, is_active=1),
    )

    updated = customer_crud.update(db, current, CustomerUpdate(industry="current", expected_version=4))

    assert updated is current
    assert current.industry == "current"
    assert current.version == 5
    db.commit.assert_called_once()


def test_customer_update_rejects_new_inactive_industry_code_before_mutation(monkeypatch):
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, industry="old", city="北京")
    locked_query = db.query.return_value.filter.return_value.with_for_update.return_value
    locked_query.first.return_value = current
    monkeypatch.setattr(
        "app.crud.industry.industry_crud.get_by_code_with_parent",
        lambda db, code: SimpleNamespace(code=code, is_active=0),
    )

    with pytest.raises(ValueError, match="行业"):
        customer_crud.update(db, current, CustomerUpdate(industry="inactive-new", expected_version=4))

    assert current.industry == "old"
    assert current.version == 4
    db.commit.assert_not_called()
