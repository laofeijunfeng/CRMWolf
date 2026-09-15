"""Regression coverage for product catalog migration portability."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

if TYPE_CHECKING:
    from types import ModuleType


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "132_product_module_catalog.py"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("product_module_catalog_132", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_product_catalog_migration_generates_ids_on_sqlite() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()

        product_id = connection.execute(
            sa.text(
                """
                INSERT INTO crm_products
                    (public_id, team_id, code, name, created_by, created_time, updated_time)
                VALUES
                    (:public_id, :team_id, :code, :name, :created_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """
            ),
            {
                "public_id": "prd_migration_test",
                "team_id": 1,
                "code": "CRM",
                "name": "CRM",
                "created_by": "migration-test",
            },
        ).scalar_one()
        module_id = connection.execute(
            sa.text(
                """
                INSERT INTO crm_product_modules
                    (
                        public_id, team_id, product_id, code, name,
                        module_role, base_key, created_by, created_time, updated_time
                    )
                VALUES
                    (
                        :public_id, :team_id, :product_id, :code, :name,
                        :module_role, :base_key, :created_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                RETURNING id
                """
            ),
            {
                "public_id": "prm_migration_test",
                "team_id": 1,
                "product_id": product_id,
                "code": "BASE",
                "module_role": "BASE",
                "base_key": "BASE",
                "name": "基础版",
                "created_by": "migration-test",
            },
        ).scalar_one()

    assert isinstance(product_id, int)
    assert product_id > 0
    assert isinstance(module_id, int)
    assert module_id > 0


def test_product_catalog_downgrade_preserves_preexisting_product_permissions() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        connection.execute(sa.text("CREATE TABLE roles (id INTEGER PRIMARY KEY, code VARCHAR(50) NOT NULL)"))
        connection.execute(
            sa.text(
                "CREATE TABLE permissions (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                "code VARCHAR(100) NOT NULL, resource VARCHAR(100) NOT NULL, "
                "action VARCHAR(50) NOT NULL, scope VARCHAR(50))"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE role_permissions (role_id INTEGER NOT NULL, permission_id INTEGER NOT NULL)"
            )
        )
        connection.execute(sa.text("INSERT INTO roles (id, code) VALUES (1, 'SALES_MEMBER')"))
        connection.execute(
            sa.text(
                "INSERT INTO permissions (id, name, code, resource, action) "
                "VALUES (1, 'Existing product view', 'product:view', 'product', 'view')"
            )
        )
        connection.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (1, 1)"))
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        migration.downgrade()

        permission = connection.execute(
            sa.text("SELECT name, code FROM permissions WHERE id = 1")
        ).one()
        grant = connection.execute(
            sa.text("SELECT role_id, permission_id FROM role_permissions WHERE role_id = 1 AND permission_id = 1")
        ).one()

    assert permission == ("Existing product view", "product:view")
    assert grant == (1, 1)


def test_product_catalog_permission_seed_sets_is_active_when_column_has_no_default() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        connection.execute(sa.text("CREATE TABLE roles (id INTEGER PRIMARY KEY, code VARCHAR(50) NOT NULL)"))
        connection.execute(
            sa.text(
                "CREATE TABLE permissions (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                "code VARCHAR(100) NOT NULL, resource VARCHAR(100) NOT NULL, "
                "action VARCHAR(50) NOT NULL, scope VARCHAR(50), is_active INTEGER NOT NULL)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE role_permissions (role_id INTEGER NOT NULL, permission_id INTEGER NOT NULL)"
            )
        )
        connection.execute(sa.text("INSERT INTO roles (id, code) VALUES (1, 'SALES_MEMBER')"))
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()

        seeded = connection.execute(
            sa.text(
                "SELECT code, is_active FROM permissions WHERE code LIKE 'product:%' ORDER BY code"
            )
        ).all()
        grant = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM role_permissions rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE p.code = 'product:view'"
            )
        ).scalar_one()

    assert seeded == [
        ("product:create", 1),
        ("product:delete", 1),
        ("product:edit", 1),
        ("product:view", 1),
    ]
    assert grant == 1


def test_product_catalog_upgrade_is_idempotent_after_partial_table_create() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        migration.upgrade()

        tables = connection.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        ).scalars().all()

    assert "crm_products" in tables
    assert "crm_product_modules" in tables
