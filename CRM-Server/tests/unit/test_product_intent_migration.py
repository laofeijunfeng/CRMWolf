"""Regression coverage for lead/customer product intent migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

if TYPE_CHECKING:
    from types import ModuleType


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "134_lead_customer_product_intent.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lead_customer_product_intent_134", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_parents(connection: sa.Connection) -> None:
    connection.execute(sa.text("CREATE TABLE crm_leads (id INTEGER PRIMARY KEY)"))
    connection.execute(sa.text("CREATE TABLE crm_customers (id INTEGER PRIMARY KEY)"))
    connection.execute(sa.text("CREATE TABLE crm_products (id INTEGER PRIMARY KEY)"))
    connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    connection.execute(
        sa.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
        {"revision": "133_opportunity_product_assignment"},
    )
    connection.commit()


def _table_names(connection: sa.Connection) -> set[str]:
    return set(
        connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type = 'table'")).scalars().all()
    )


def _index_names(connection: sa.Connection) -> set[str]:
    return set(
        connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type = 'index'")).scalars().all()
    )


def test_intent_migration_revision_follows_opportunity_product_assignment() -> None:
    migration = _load_migration()
    assert migration.revision == "134_lead_customer_product_intent"
    assert migration.down_revision == "133_opportunity_product_assignment"


def test_intent_migration_upgrade_creates_tables_and_indexes() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        _prepare_parents(connection)
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        connection.execute(
            sa.text("UPDATE alembic_version SET version_num = :revision"),
            {"revision": migration.revision},
        )
        connection.commit()

        tables = _table_names(connection)
        indexes = _index_names(connection)
        lead_index_list = connection.execute(sa.text("PRAGMA index_list('crm_lead_products')")).all()
        customer_index_list = connection.execute(sa.text("PRAGMA index_list('crm_customer_products')")).all()

    assert "crm_lead_products" in tables
    assert "crm_customer_products" in tables
    assert "idx_lead_products_team" in indexes
    assert "idx_lead_products_product" in indexes
    assert "idx_customer_products_team" in indexes
    assert "idx_customer_products_product" in indexes

    unique_lead_indexes = {row[1] for row in lead_index_list if row[2]}
    unique_customer_indexes = {row[1] for row in customer_index_list if row[2]}
    assert "idx_lead_products_team" not in unique_lead_indexes
    assert "idx_customer_products_team" not in unique_customer_indexes


def test_intent_migration_allows_multiple_products_per_owner() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        _prepare_parents(connection)
        connection.execute(sa.text("INSERT INTO crm_leads (id) VALUES (1)"))
        connection.execute(sa.text("INSERT INTO crm_customers (id) VALUES (1)"))
        connection.execute(sa.text("INSERT INTO crm_products (id) VALUES (1), (2)"))
        connection.commit()
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()

        connection.execute(
            sa.text(
                "INSERT INTO crm_lead_products (lead_id, product_id, team_id) VALUES (1, 1, 1), (1, 2, 1)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO crm_customer_products (customer_id, product_id, team_id) "
                "VALUES (1, 1, 1), (1, 2, 1)"
            )
        )
        connection.commit()
        lead_count = connection.execute(sa.text("SELECT COUNT(*) FROM crm_lead_products")).scalar_one()
        customer_count = connection.execute(sa.text("SELECT COUNT(*) FROM crm_customer_products")).scalar_one()

    assert lead_count == 2
    assert customer_count == 2


def test_intent_migration_downgrade_drops_tables_and_restores_revision_133() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        _prepare_parents(connection)
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        connection.execute(
            sa.text("UPDATE alembic_version SET version_num = :revision"),
            {"revision": migration.revision},
        )
        connection.commit()

        migration.downgrade()
        connection.execute(
            sa.text("UPDATE alembic_version SET version_num = :revision"),
            {"revision": migration.down_revision},
        )
        connection.commit()

        tables = _table_names(connection)
        indexes = _index_names(connection)
        version = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()

    assert "crm_lead_products" not in tables
    assert "crm_customer_products" not in tables
    assert "idx_lead_products_team" not in indexes
    assert "idx_lead_products_product" not in indexes
    assert "idx_customer_products_team" not in indexes
    assert "idx_customer_products_product" not in indexes
    assert version == "133_opportunity_product_assignment"
