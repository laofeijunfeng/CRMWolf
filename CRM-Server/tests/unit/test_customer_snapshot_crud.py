from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.exceptions import ConflictException
from app.crud.customer import customer_crud
from app.models.customer import Customer
from app.schemas.customer import CustomerLicenseSnapshotUpdate, CustomerUpdate


def _locked_customer(db, customer):
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
    locked_query.first.return_value = customer
    return locked_query


def _locked_customer_for_update(db: MagicMock, **overrides: object) -> SimpleNamespace:
    values = {
        "id": 1,
        "team_id": 9,
        "version": 4,
        "account_name": "测试客户",
        "city": "北京",
        "address": None,
        "company_scale": "1-50人",
        "source_id": None,
        "source": None,
        "industry": "internet_saas",
        "status": 0,
        "license_type": "TRIAL",
        "license_expiry_date": date(2026, 1, 1),
    }
    values.update(overrides)
    customer = SimpleNamespace(**values)
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
    locked_query.first.return_value = customer
    return customer


def _sqlite_customer_sessions(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'customer-lock-refresh.db'}")
    Base.metadata.create_all(engine, tables=[Customer.__table__])
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    seed = session_factory()
    seed.add(
        Customer(
            id=1,
            public_id="cus-lock-refresh",
            team_id=9,
            account_name="锁刷新客户",
            city="北京",
            creator_id="tester",
            version=4,
            license_type="TRIAL",
            license_expiry_date=date(2026, 1, 1),
            status=0,
        )
    )
    seed.commit()
    seed.close()
    return engine, session_factory



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
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
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
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
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
    assert current.version == 4
    db.commit.assert_not_called()



def test_customer_update_accepts_active_industry_code(monkeypatch):
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, industry="old", city="北京")
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
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
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
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


def test_update_license_snapshot_rejects_stale_version_after_concurrent_commit(tmp_path):
    engine, session_factory = _sqlite_customer_sessions(tmp_path)
    session_a = session_factory()
    session_b = session_factory()
    session_c = session_factory()
    try:
        customer_a = session_a.query(Customer).filter(Customer.id == 1).first()
        session_a.commit()

        customer_b = session_b.query(Customer).filter(Customer.id == 1).first()
        customer_b.license_type = "OFFICIAL"
        customer_b.license_expiry_date = date(2028, 1, 1)
        customer_b.version = 5
        session_b.commit()

        payload = CustomerLicenseSnapshotUpdate(
            expected_version=4,
            license_type="OFFICIAL",
            license_expiry_date=date(2030, 1, 1),
        )
        with pytest.raises(ConflictException):
            customer_crud.update_license_snapshot(session_a, customer_a, payload)

        latest = session_c.query(Customer).filter(Customer.id == 1).one()
        assert latest.license_type == "OFFICIAL"
        assert latest.license_expiry_date == date(2028, 1, 1)
        assert latest.version == 5
    finally:
        session_a.close()
        session_b.close()
        session_c.close()
        engine.dispose()


@pytest.mark.parametrize("current_status", [2, 3])
def test_update_with_audit_rejects_status_write_from_read_only_customer(current_status: int) -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db, status=current_status)

    with pytest.raises(ValueError, match="仅允许更新跟进中或已成交客户的状态"):
        customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, status=1),
        )

    assert customer.status == current_status
    assert customer.version == 4
    db.commit.assert_not_called()


def test_update_with_audit_rejects_new_inactive_industry_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db)
    monkeypatch.setattr(
        "app.crud.customer.industry_crud.get_by_code_with_parent",
        lambda db_session, code: SimpleNamespace(code=code, is_active=0),
    )

    with pytest.raises(ValueError, match="行业代码不存在或已停用"):
        customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, industry="inactive_new"),
        )

    assert customer.industry == "internet_saas"
    assert customer.version == 4
    db.commit.assert_not_called()


def test_update_with_audit_resolves_partial_license_date_against_current_type() -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.crud.customer.industry_crud.get_by_code_with_parent",
        lambda db_session, code: SimpleNamespace(code=code, is_active=1),
    )
    try:
        updated, before, after = customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, license_expiry_date=date(2027, 1, 1)),
        )
    finally:
        monkeypatch.undo()

    assert updated is customer
    assert customer.license_type == "TRIAL"
    assert customer.license_expiry_date == date(2027, 1, 1)
    assert before == {"license_expiry_date": date(2026, 1, 1)}
    assert after == {"license_expiry_date": date(2027, 1, 1)}
    assert customer.version == 5
    db.commit.assert_called_once()


def test_update_with_audit_rejects_effective_license_pair_without_type() -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db, license_type=None, license_expiry_date=None)

    with pytest.raises(ValueError, match="授权到期日期不为空时必须选择授权类型"):
        customer_crud.update_with_audit(
            db,
            customer,
            CustomerUpdate(expected_version=4, license_expiry_date=date(2027, 1, 1)),
        )

    assert customer.license_type is None
    assert customer.license_expiry_date is None
    assert customer.version == 4
    db.commit.assert_not_called()


def test_update_with_audit_does_not_increment_version_for_no_actual_change() -> None:
    db = MagicMock()
    customer = _locked_customer_for_update(db)

    updated, before, after = customer_crud.update_with_audit(
        db,
        customer,
        CustomerUpdate(expected_version=4, city="北京"),
    )

    assert updated is customer
    assert before == {}
    assert after == {}
    assert customer.version == 4
    db.commit.assert_not_called()

