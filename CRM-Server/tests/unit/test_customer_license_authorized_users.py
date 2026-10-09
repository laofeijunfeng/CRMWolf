"""Customer License authorized-user snapshot projection tests."""

from datetime import date, datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud import crud_license_application as license_crud_module
from app.crud.crud_license_application import license_application_crud
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.license_application import LicenseApplication, LicenseApplicationStatus


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerLegacySourceProgress.__table__,
            LicenseApplication.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _customer(*, team_id=1, customer_id=None):
    kwargs = {
        "team_id": team_id,
        "account_name": "测试客户",
        "city": "上海",
        "creator_id": "tester",
        "owner_id": "tester",
    }
    if customer_id is not None:
        kwargs["id"] = customer_id
    return Customer(**kwargs)


def _application(
    application_number,
    *,
    customer_id=1,
    team_id=1,
    status=LicenseApplicationStatus.ISSUED,
    license_type="OFFICIAL",
    users=20,
    expiry=date(2028, 1, 1),
    modified=datetime(2026, 1, 1),
    application_id=None,
):
    kwargs = {
        "team_id": team_id,
        "application_number": application_number,
        "customer_id": customer_id,
        "expiry_date": expiry,
        "license_type": license_type,
        "authorized_users": users,
        "status": status,
        "applicant_id": "tester",
        "created_time": modified,
        "last_modified_time": modified,
    }
    if application_id is not None:
        kwargs["id"] = application_id
    return LicenseApplication(**kwargs)


@pytest.fixture
def customer(db):
    row = _customer()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _disable_progress_side_effect(monkeypatch):
    monkeypatch.setattr(license_crud_module, "advance_eligible_progress", lambda *args, **kwargs: None)


def _progress(db, customer_id=1, team_id=1):
    return db.query(CustomerLegacySourceProgress).filter_by(
        team_id=team_id, customer_id=customer_id
    ).one_or_none()


def test_customer_model_exposes_nullable_license_authorized_users(db):
    customer = _customer()
    db.add(customer)
    db.commit()
    assert customer.license_authorized_users is None


def test_snapshot_ignores_non_issued_and_accepts_trial_and_official(db, customer, monkeypatch):
    db.add_all([
        _application("draft", status="DRAFT", license_type="OFFICIAL", users=99, expiry=date(2030, 1, 1)),
        _application("trial", status=LicenseApplicationStatus.ISSUED, license_type="TRIAL", users=5, expiry=date(2027, 1, 1)),
        _application("official", status=LicenseApplicationStatus.ISSUED, license_type="OFFICIAL", users=20, expiry=date(2028, 1, 1)),
    ])
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(
        db, 1, db.query(LicenseApplication).filter_by(application_number="trial").one()
    )
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "OFFICIAL", 20, date(2028, 1, 1)
    )


def test_snapshot_prefers_later_expiry_then_last_modified_then_id(db, customer, monkeypatch):
    same_expiry_older_time = _application(
        "older-time", license_type="TRIAL", users=1, expiry=date(2028, 1, 1), modified=datetime(2026, 1, 1)
    )
    same_expiry_newer_time = _application(
        "newer-time", license_type="OFFICIAL", users=2, expiry=date(2028, 1, 1), modified=datetime(2026, 2, 1)
    )
    same_expiry_same_time_low_id = _application(
        "low-id", license_type="TRIAL", users=3, expiry=date(2029, 1, 1), modified=datetime(2026, 3, 1), application_id=10
    )
    same_expiry_same_time_high_id = _application(
        "high-id", license_type="OFFICIAL", users=4, expiry=date(2029, 1, 1), modified=datetime(2026, 3, 1), application_id=11
    )
    db.add_all([
        same_expiry_older_time,
        same_expiry_newer_time,
        same_expiry_same_time_low_id,
        same_expiry_same_time_high_id,
    ])
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, same_expiry_older_time)
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "OFFICIAL", 4, date(2029, 1, 1)
    )


def test_snapshot_takes_all_values_from_selected_application(db, customer, monkeypatch):
    selected = _application(
        "selected", license_type="TRIAL", users=7, expiry=date(2029, 1, 1), modified=datetime(2026, 2, 1)
    )
    competing = _application(
        "competing", license_type="OFFICIAL", users=99, expiry=date(2028, 1, 1), modified=datetime(2026, 3, 1)
    )
    db.add_all([selected, competing])
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, competing)
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "TRIAL", 7, date(2029, 1, 1)
    )


def test_cross_team_issued_application_leaves_customer_unchanged(db, customer, monkeypatch):
    application = _application(
        "other-team", team_id=2, license_type="TRIAL", users=7, expiry=date(2029, 1, 1)
    )
    db.add(application)
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, application)
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (None, None, None)


def test_missing_customer_is_a_noop(db, monkeypatch):
    application = _application("missing", customer_id=999, license_type="TRIAL", users=7, expiry=date(2029, 1, 1))
    db.add(application)
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, application)

    assert db.query(Customer).count() == 0
    assert db.query(CustomerLegacySourceProgress).count() == 0


def test_no_issued_applications_clear_all_snapshot_fields(db, customer, monkeypatch):
    customer.license_type = "OFFICIAL"
    customer.license_authorized_users = 20
    customer.license_expiry_date = date(2028, 1, 1)
    application = _application("now-rejected", status="REJECTED", license_type="TRIAL", users=5, expiry=date(2029, 1, 1))
    db.add(application)
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, application)
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (None, None, None)


def test_older_issued_application_does_not_replace_newer_snapshot(db, customer, monkeypatch):
    newer = _application("newer", license_type="OFFICIAL", users=20, expiry=date(2029, 1, 1), modified=datetime(2026, 2, 1))
    older = _application("older", license_type="TRIAL", users=5, expiry=date(2028, 1, 1), modified=datetime(2026, 3, 1))
    db.add_all([newer, older])
    db.commit()
    license_application_crud.update_customer_license_info(db, 1, newer)
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, older)
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "OFFICIAL", 20, date(2029, 1, 1)
    )


def test_older_application_recomputes_snapshot_after_prior_winner_is_no_longer_eligible(db, customer, monkeypatch):
    newer = _application("newer", license_type="OFFICIAL", users=20, expiry=date(2029, 1, 1), modified=datetime(2026, 2, 1))
    older = _application("older", license_type="TRIAL", users=5, expiry=date(2028, 1, 1), modified=datetime(2026, 1, 1))
    db.add_all([newer, older])
    db.commit()
    license_application_crud.update_customer_license_info(db, 1, newer)
    db.refresh(customer)
    newer.status = "REJECTED"
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, older)
    db.refresh(customer)

    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "TRIAL", 5, date(2028, 1, 1)
    )


def test_equal_expiry_type_and_user_change_does_not_advance_progress_twice(db, customer, monkeypatch):
    calls = []
    monkeypatch.setattr(
        license_crud_module,
        "advance_eligible_progress",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    first = _application("first", license_type="TRIAL", users=5, expiry=date(2028, 1, 1), modified=datetime(2026, 1, 1))
    db.add(first)
    db.commit()

    license_application_crud.update_customer_license_info(db, 1, first)
    db.refresh(customer)
    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "TRIAL", 5, date(2028, 1, 1)
    )

    second = _application("second", license_type="OFFICIAL", users=20, expiry=date(2028, 1, 1), modified=datetime(2026, 2, 1))
    db.add(second)
    db.commit()

    license_application_crud.update_customer_license_info(db, 1, second)
    db.refresh(customer)

    assert len(calls) == 1
    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "OFFICIAL", 20, date(2028, 1, 1)
    )


def test_commit_true_does_not_commit_unrelated_pending_changes_when_snapshot_is_unchanged(
    db, customer, monkeypatch
):
    application = _application("unchanged", license_type="OFFICIAL", users=20, expiry=date(2028, 1, 1))
    db.add(application)
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    customer.license_type = "OFFICIAL"
    customer.license_authorized_users = 20
    customer.license_expiry_date = date(2028, 1, 1)
    db.commit()

    unrelated = _customer(customer_id=2)
    unrelated.account_name = "待提交客户"
    unrelated.account_name_norm = "待提交客户"
    db.add(unrelated)
    db.commit()
    unrelated.account_name = "pending change"

    license_application_crud.update_customer_license_info(db, 1, application, commit=True)
    db.rollback()

    assert db.query(Customer).filter_by(id=unrelated.id).one().account_name == "待提交客户"



def test_commit_false_defers_snapshot_persistence_until_commit(db, customer, monkeypatch):
    application = _application("deferred", license_type="TRIAL", users=5, expiry=date(2028, 1, 1))
    db.add(application)
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, application, commit=False)
    db.rollback()
    db.refresh(customer)
    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (None, None, None)

    license_application_crud.update_customer_license_info(db, 1, application, commit=False)
    db.commit()
    db.refresh(customer)
    assert (customer.license_type, customer.license_authorized_users, customer.license_expiry_date) == (
        "TRIAL", 5, date(2028, 1, 1)
    )


def test_commit_true_persists_snapshot(db, customer, monkeypatch):
    application = _application("committed", license_type="OFFICIAL", users=20, expiry=date(2028, 1, 1))
    db.add(application)
    db.commit()
    _disable_progress_side_effect(monkeypatch)

    license_application_crud.update_customer_license_info(db, 1, application, commit=True)
    db.expire_all()
    persisted = db.query(Customer).filter_by(id=customer.id).one()

    assert (persisted.license_type, persisted.license_authorized_users, persisted.license_expiry_date) == (
        "OFFICIAL", 20, date(2028, 1, 1)
    )
