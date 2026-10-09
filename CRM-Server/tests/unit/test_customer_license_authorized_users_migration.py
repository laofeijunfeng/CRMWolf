"""Verify historical customer License authorization snapshot backfill."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "151_customer_license_authorized_users.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "customer_license_authorized_users_151", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_schema(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            CREATE TABLE crm_customers (
                id INTEGER PRIMARY KEY,
                team_id INTEGER NOT NULL,
                license_type VARCHAR(20),
                license_expiry_date DATE
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE TABLE crm_license_applications (
                id INTEGER PRIMARY KEY,
                team_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                expiry_date DATE NOT NULL,
                license_type VARCHAR(20) NOT NULL,
                authorized_users INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                last_modified_time DATETIME NOT NULL
            )
            """
        )
    )
    connection.commit()


def _seed_data(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO crm_customers (id, team_id, license_type, license_expiry_date)
            VALUES
                (1, 1, NULL, NULL),
                (2, 1, 'TRIAL', '2027-01-01'),
                (3, 2, 'OFFICIAL', '2027-06-01')
            """
        )
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO crm_license_applications
                (id, team_id, customer_id, expiry_date, license_type,
                 authorized_users, status, last_modified_time)
            VALUES
                (1, 1, 1, '2035-01-01', 'TRIAL', 99, 'DRAFT', '2026-03-01 00:00:00'),
                (10, 1, 1, '2028-01-01', 'TRIAL', 5, 'ISSUED', '2026-01-01 00:00:00'),
                (11, 1, 1, '2029-01-01', 'TRIAL', 7, 'ISSUED', '2026-01-02 00:00:00'),
                (12, 1, 1, '2029-01-01', 'TRIAL', 17, 'ISSUED', '2026-02-01 00:00:00'),
                (13, 1, 1, '2029-01-01', 'OFFICIAL', 42, 'ISSUED', '2026-02-01 00:00:00'),
                (20, 1, 2, '2030-01-01', 'OFFICIAL', 88, 'REJECTED', '2026-04-01 00:00:00'),
                (30, 1, 3, '2031-01-01', 'OFFICIAL', 66, 'ISSUED', '2026-05-01 00:00:00')
            """
        )
    )
    connection.commit()


def _column_names(connection: sa.Connection, table_name: str) -> set[str]:
    return {column[1] for column in connection.execute(sa.text(f"PRAGMA table_info('{table_name}')"))}


def _customer_snapshot(connection: sa.Connection, customer_id: int) -> tuple[str | None, int | None, object]:
    row = connection.execute(
        sa.text(
            "SELECT license_type, license_authorized_users, license_expiry_date "
            "FROM crm_customers WHERE id = :customer_id"
        ),
        {"customer_id": customer_id},
    ).one()
    return row[0], row[1], row[2]


def test_migration_revision_follows_current_head() -> None:
    migration = _load_migration()

    assert migration.revision == "151_customer_license_authorized_users"
    assert migration.down_revision == "150_profile_version_attestation"


def test_migration_backfills_same_winner_and_downgrades_cleanly() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    migration = _load_migration()

    with engine.connect() as connection:
        _prepare_schema(connection)
        _seed_data(connection)
        assert "license_authorized_users" not in _column_names(connection, "crm_customers")

        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()
        connection.commit()

        assert "license_authorized_users" in _column_names(connection, "crm_customers")
        assert _customer_snapshot(connection, customer_id=1) == (
            "OFFICIAL",
            42,
            "2029-01-01",
        )
        assert _customer_snapshot(connection, customer_id=2) == (None, None, None)
        assert _customer_snapshot(connection, customer_id=3) == (None, None, None)

        migration.downgrade()
        connection.commit()

        assert "license_authorized_users" not in _column_names(connection, "crm_customers")
        assert connection.execute(
            sa.text(
                "SELECT license_type, license_expiry_date "
                "FROM crm_customers WHERE id = 1"
            )
        ).one() == ("OFFICIAL", "2029-01-01")
