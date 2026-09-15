from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.exceptions import ConflictException
from app.crud.customer import customer_crud
from app.models.customer import Customer
from app.schemas.customer import CustomerUpdate


def test_customer_update_carries_expected_version_for_optimistic_locking() -> None:
    payload = CustomerUpdate(account_name="新客户名称", expected_version=7)

    assert payload.expected_version == 7


def test_customer_update_rejects_invalid_expected_version() -> None:
    with pytest.raises(ValidationError):
        CustomerUpdate(expected_version=0)


def test_customer_update_rejects_a_stale_version_before_mutating() -> None:
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, city="北京")
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
    locked_query.first.return_value = current

    with pytest.raises(ConflictException, match="已发生变化"):
        customer_crud.update(db, current, CustomerUpdate(city="上海", expected_version=3))

    assert current.city == "北京"
    db.commit.assert_not_called()


def test_customer_update_locks_and_updates_when_version_matches() -> None:
    db = MagicMock()
    current = SimpleNamespace(id=1, version=4, team_id=9, city="北京")
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
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
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda db, current, payload: (
            setattr(current, "city", payload.city) or (current, {"city": "北京"}, {"city": payload.city})
        ),
    )

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


def test_update_customer_logs_source_public_id_changes(monkeypatch) -> None:
    from app.api import customers as customers_api

    previous_source = SimpleNamespace(id=11, public_id="src_old", name="旧来源")
    next_source = SimpleNamespace(id=22, public_id="src_new", name="新来源")
    customer = SimpleNamespace(
        id=1,
        public_id="cus_1",
        team_id=9,
        source_id=11,
        source="旧来源",
        version=4,
    )
    user = SimpleNamespace(id=7, name="操作人")
    logged = []
    monkeypatch.setattr(customers_api, "_get_editable_customer", lambda *args: customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda db, current, payload: (
            setattr(current, "source_id", 22)
            or setattr(current, "source", "新来源")
            or (current, {"source_public_id": "src_old"}, {"source_public_id": "src_new"})
        ),
    )

    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: None)
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)
    monkeypatch.setattr(
        customers_api,
        "get_by_id",
        lambda db, source_id, team_id: {11: previous_source, 22: next_source}.get(source_id),
    )
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: logged.append(kwargs))

    result = customers_api.update_customer(
        "cus_1",
        CustomerUpdate(source_public_id="src_new", expected_version=4),
        team_id=9,
        current_user=user,
        db=MagicMock(),
    )

    assert result is customer
    assert logged[0]["content"] == {
        "changed_fields": ["source_public_id"],
        "before": {"source_public_id": "src_old"},
        "after": {"source_public_id": "src_new"},
    }
    assert "source_id" not in logged[0]["content"]["before"]
    assert "source_id" not in logged[0]["content"]["after"]


def test_update_customer_logs_both_submitted_source_fields(monkeypatch) -> None:
    from app.api import customers as customers_api

    previous_source = SimpleNamespace(id=11, public_id="src_old", name="旧来源")
    next_source = SimpleNamespace(id=22, public_id="src_new", name="新来源")
    customer = SimpleNamespace(
        id=1,
        public_id="cus_1",
        team_id=9,
        source_id=11,
        source="旧来源",
        version=4,
    )
    user = SimpleNamespace(id=7, name="操作人")
    logged = []
    monkeypatch.setattr(customers_api, "_get_editable_customer", lambda *args: customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda db, current, payload: (
            setattr(current, "source_id", 22)
            or setattr(current, "source", "新来源")
            or (current, {"source_public_id": "src_old"}, {"source_public_id": "src_new"})
        ),
    )

    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: None)
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)
    monkeypatch.setattr(
        customers_api,
        "get_by_id",
        lambda db, source_id, team_id: {11: previous_source, 22: next_source}.get(source_id),
    )
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: logged.append(kwargs))

    result = customers_api.update_customer(
        "cus_1",
        CustomerUpdate(source_public_id="src_new", source="新来源", expected_version=4),
        team_id=9,
        current_user=user,
        db=MagicMock(),
    )

    assert result is customer
    assert logged[0]["content"] == {
        "changed_fields": ["source_public_id"],
        "before": {"source_public_id": "src_old"},
        "after": {"source_public_id": "src_new"},
    }

    assert "source_id" not in logged[0]["content"]["before"]
    assert "source_id" not in logged[0]["content"]["after"]


def _sqlite_customer_sessions(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'customer-update-lock-refresh.db'}")
    Base.metadata.create_all(engine, tables=[Customer.__table__])
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    seed = session_factory()
    seed.add(
        Customer(
            id=1,
            public_id="cus-update-lock-refresh",
            team_id=9,
            account_name="更新锁刷新客户",
            city="北京",
            creator_id="tester",
            version=4,
            status=0,
        )
    )
    seed.commit()
    seed.close()
    return engine, session_factory


def test_customer_update_rejects_stale_version_after_concurrent_commit(tmp_path: Path) -> None:
    engine, session_factory = _sqlite_customer_sessions(tmp_path)
    session_a = session_factory()
    session_b = session_factory()
    session_c = session_factory()
    try:
        customer_a = session_a.query(Customer).filter(Customer.id == 1).first()
        assert customer_a is not None
        session_a.commit()

        customer_b = session_b.query(Customer).filter(Customer.id == 1).first()
        assert customer_b is not None
        customer_b.city = "深圳"
        customer_b.version = 5
        session_b.commit()

        with pytest.raises(ConflictException):
            customer_crud.update(
                session_a,
                customer_a,
                CustomerUpdate(city="上海", expected_version=4),
            )

        latest = session_c.query(Customer).filter(Customer.id == 1).one()
        assert latest.city == "深圳"
        assert latest.version == 5
    finally:
        session_a.close()
        session_b.close()
        session_c.close()
        engine.dispose()


def test_customer_update_increments_version_once_for_combined_more_information_fields(monkeypatch) -> None:
    db = MagicMock()
    current = SimpleNamespace(
        id=1,
        version=4,
        team_id=9,
        city="北京",
        industry="internet_saas",
        status=0,
        license_type="TRIAL",
        license_expiry_date=None,
    )
    locked_query = db.query.return_value.filter.return_value.populate_existing.return_value.with_for_update.return_value
    locked_query.first.return_value = current
    monkeypatch.setattr(
        "app.crud.customer.industry_crud.get_by_code_with_parent",
        lambda db_session, code: SimpleNamespace(code=code, is_active=1),
    )

    updated = customer_crud.update(
        db,
        current,
        CustomerUpdate(
            expected_version=4,
            industry="finance_securities",
            status=1,
            license_type="OFFICIAL",
            license_expiry_date=date(2027, 1, 1),
        ),
    )

    assert updated is current
    assert current.industry == "finance_securities"
    assert current.status == 1
    assert current.license_type == "OFFICIAL"
    assert current.version == 5
    db.commit.assert_called_once()


def test_update_customer_skips_audit_and_refresh_for_noop(monkeypatch) -> None:
    from app.api import customers as customers_api

    customer = SimpleNamespace(
        id=1,
        public_id="cus_1",
        team_id=9,
        city="北京",
        version=4,
    )
    user = SimpleNamespace(id=7, name="操作人")
    logged = []
    refreshes = []
    monkeypatch.setattr(customers_api, "_get_editable_customer", lambda *args: customer)
    monkeypatch.setattr(
        customers_api.customer_crud,
        "update_with_audit",
        lambda db, current, payload: (current, {}, {}),
    )
    monkeypatch.setattr(customers_api, "_persist_customer_business_object_refresh_after_commit", lambda **kwargs: refreshes.append(kwargs))
    monkeypatch.setattr(customers_api, "_customer_response", lambda db, updated: updated)
    monkeypatch.setattr(customers_api.operation_log_service, "log", lambda **kwargs: logged.append(kwargs))

    result = customers_api.update_customer(
        "cus_1",
        CustomerUpdate(city="北京", expected_version=4),
        team_id=9,
        current_user=user,
        db=MagicMock(),
    )

    assert result is customer
    assert customer.version == 4
    assert logged == []
    assert refreshes == []
