"""Customer names that are Unicode-compatibility equivalent must not coexist in one team."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api import customers as customer_api
from app.core.database import Base
from app.crud.customer import customer_crud
from app.models.customer import Customer

RADICAL_NAME = "中国对外贸易中\u2f3c集团有限公司"  # U+2F3C KANGXI RADICAL HEART
STANDARD_NAME = "中国对外贸易中\u5fc3集团有限公司"  # U+5FC3 心

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "162_customer_name_dedupe_key.py"
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[Customer.__table__])
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _customer(db, name: str, *, team_id: int = 1) -> Customer:
    customer = Customer(team_id=team_id, account_name=name, city="上海", creator_id="1")
    db.add(customer)
    db.commit()
    return customer


def test_equivalent_name_in_same_team_is_reported_as_existing(session, monkeypatch):
    _customer(session, RADICAL_NAME)
    monkeypatch.setattr(customer_api.lead_crud, "get_by_name", lambda db, name, team_id: None)

    with pytest.raises(HTTPException) as exc_info:
        customer_api._ensure_customer_name_available(session, STANDARD_NAME, 1)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "客户名称已存在"


@pytest.mark.parametrize(
    "variant",
    [
        "\u3000" + STANDARD_NAME + "\u00a0",  # ideographic / no-break spaces around
        "中国对外贸易\u200b中心集团有限公司",  # zero-width space inside
        "ＡＢＣ科技",  # full-width latin
    ],
)
def test_invisible_and_width_variants_resolve_to_existing_customer(session, variant):
    existing = _customer(session, "ABC科技" if variant == "ＡＢＣ科技" else STANDARD_NAME)

    assert customer_crud.get_by_name(session, variant, team_id=1).id == existing.id


def test_distinct_legal_suffix_is_not_a_duplicate(session):
    _customer(session, "睿狐科技有限公司")

    assert customer_crud.get_by_name(session, "睿狐科技", team_id=1) is None


def test_database_rejects_equivalent_name_in_same_team(session):
    _customer(session, RADICAL_NAME)

    with pytest.raises(IntegrityError):
        _customer(session, STANDARD_NAME)


def test_equivalent_name_is_allowed_in_another_team(session):
    _customer(session, RADICAL_NAME, team_id=1)
    other = _customer(session, STANDARD_NAME, team_id=2)

    assert customer_crud.get_by_name(session, RADICAL_NAME, team_id=2).id == other.id


def test_database_rejects_rename_into_equivalent_name(session):
    _customer(session, STANDARD_NAME)
    renamed = _customer(session, "其他公司")

    renamed.account_name = RADICAL_NAME
    with pytest.raises(IntegrityError):
        session.commit()


def _load_migration():
    spec = importlib.util.spec_from_file_location("customer_name_dedupe_key_162", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_backfills_keys_and_tolerates_legacy_equivalent_rows():
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        connection.execute(
            sa.text("CREATE TABLE crm_customers (id INTEGER PRIMARY KEY, team_id INTEGER, account_name VARCHAR(255))")
        )
        connection.execute(
            sa.text("INSERT INTO crm_customers (id, team_id, account_name) VALUES (:id, :team, :name)"),
            [
                {"id": 199, "team": 1, "name": RADICAL_NAME},
                {"id": 243, "team": 1, "name": STANDARD_NAME},
                {"id": 300, "team": 2, "name": STANDARD_NAME},
            ],
        )
        connection.commit()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.commit()

        rows = connection.execute(
            sa.text("SELECT id, account_name, account_name_dedupe_key FROM crm_customers ORDER BY id")
        ).all()
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO crm_customers (id, team_id, account_name, account_name_dedupe_key) "
                    "VALUES (400, 1, :name, :key)"
                ),
                {"name": STANDARD_NAME + " ", "key": STANDARD_NAME},
            )

    assert rows == [
        (199, RADICAL_NAME, STANDARD_NAME),
        (243, STANDARD_NAME, None),
        (300, STANDARD_NAME, STANDARD_NAME),
    ]
