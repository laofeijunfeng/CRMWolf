"""Regression coverage for product catalog migration portability."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

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
                    (public_id, team_id, product_id, code, name, created_by, created_time, updated_time)
                VALUES
                    (:public_id, :team_id, :product_id, :code, :name, :created_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """
            ),
            {
                "public_id": "prm_migration_test",
                "team_id": 1,
                "product_id": product_id,
                "code": "BASE",
                "name": "基础版",
                "created_by": "migration-test",
            },
        ).scalar_one()

    assert isinstance(product_id, int)
    assert product_id > 0
    assert isinstance(module_id, int)
    assert module_id > 0
