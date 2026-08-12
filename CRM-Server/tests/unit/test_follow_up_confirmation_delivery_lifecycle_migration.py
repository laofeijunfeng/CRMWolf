"""Regression tests for legacy confirmation delivery audit repair."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/081_follow_up_confirmation_delivery_lifecycle.py"
)


def _load_migration_module():
    spec = spec_from_file_location("follow_up_confirmation_delivery_lifecycle_081", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_duplicate_prompt_key_repair_preserves_all_audit_rows_deterministically():
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    deliveries = sa.Table(
        "deliveries",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, nullable=False),
        sa.Column("prompt_key", sa.String(128), nullable=False),
    )
    metadata.create_all(engine)
    original_key = "projection:" + "x" * 140

    with engine.begin() as connection:
        connection.execute(deliveries.insert(), [
            {"id": 10, "team_id": 1, "prompt_key": original_key},
            {"id": 11, "team_id": 1, "prompt_key": original_key},
            {"id": 12, "team_id": 1, "prompt_key": original_key},
            {"id": 13, "team_id": 2, "prompt_key": original_key},
        ])

        repaired = migration.repair_duplicate_prompt_keys(connection, table_name="deliveries")
        rows = connection.execute(
            sa.select(deliveries.c.id, deliveries.c.team_id, deliveries.c.prompt_key).order_by(deliveries.c.id)
        ).all()

    assert repaired == 2
    assert len(rows) == 4
    assert rows[0].prompt_key == original_key
    assert rows[1].prompt_key.endswith(":legacy:11")
    assert rows[2].prompt_key.endswith(":legacy:12")
    assert len(rows[1].prompt_key) == 128
    assert len(rows[2].prompt_key) == 128
    assert rows[3].prompt_key == original_key
    assert len({(row.team_id, row.prompt_key) for row in rows}) == 4


def test_duplicate_prompt_key_repair_avoids_preexisting_legacy_repair_keys():
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    deliveries = sa.Table(
        "deliveries",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, nullable=False),
        sa.Column("prompt_key", sa.String(128), nullable=False),
    )
    metadata.create_all(engine)
    original_key = "projection:" + "x" * 140
    legacy_suffix = ":legacy:11"
    preexisting_repair_key = f"{original_key[: 128 - len(legacy_suffix)]}{legacy_suffix}"

    with engine.begin() as connection:
        connection.execute(deliveries.insert(), [
            {"id": 10, "team_id": 1, "prompt_key": original_key},
            {"id": 11, "team_id": 1, "prompt_key": original_key},
            {"id": 99, "team_id": 1, "prompt_key": preexisting_repair_key},
        ])

        repaired = migration.repair_duplicate_prompt_keys(connection, table_name="deliveries")
        rows = connection.execute(
            sa.select(deliveries.c.id, deliveries.c.prompt_key).order_by(deliveries.c.id)
        ).all()

    assert repaired == 1
    assert len({row.prompt_key for row in rows}) == 3
    assert rows[1].prompt_key != preexisting_repair_key
    assert len(rows[1].prompt_key) <= 128
