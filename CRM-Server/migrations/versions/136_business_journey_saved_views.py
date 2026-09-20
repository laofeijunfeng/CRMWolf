"""migrate legacy business journey board saved views

Revision ID: 136_business_journey_saved_views
Revises: 135_deal_journey_public_ids
Create Date: 2026-09-20

"""
from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from typing import Any

import sqlalchemy as sa
from alembic import op


revision: str = "136_business_journey_saved_views"
down_revision: str | None = "135_deal_journey_public_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "crm_view_preferences"
_ORIGIN_TABLE_NAME = "_migration_136_saved_view_origins"
_LEGACY_VIEW_KEY = "business-journey-board.board"
_TARGET_VIEW_KEY = "business-journeys.list"
_OWNER_KEY_COLUMNS = ("team_id", "scope", "user_id", "preference_key")
_RENAMED_ORIGIN = "renamed"
_COLLISION_ORIGIN = "collision"


def _load_table(connection: sa.Connection) -> sa.Table | None:
    if not sa.inspect(connection).has_table(_TABLE_NAME):
        return None
    return sa.Table(_TABLE_NAME, sa.MetaData(), autoload_with=connection)


def _parse_config(raw_config: str) -> dict[str, Any] | None:
    try:
        config = json.loads(raw_config)
    except (TypeError, json.JSONDecodeError):
        return None
    return config if isinstance(config, dict) else None


def _serialize_config(config: dict[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


def _canonical_config(config: dict[str, Any]) -> dict[str, Any]:
    canonical = dict(config)
    canonical.setdefault("version", 1)
    canonical.setdefault("columns", [])
    canonical.setdefault("sorts", [])
    canonical.setdefault("filters", [])
    canonical.setdefault("density", None)

    columns = canonical["columns"]
    if isinstance(columns, list):
        normalized_columns: list[Any] = []
        for column in columns:
            if not isinstance(column, dict):
                normalized_columns.append(column)
                continue
            normalized_column = dict(column)
            normalized_column.setdefault("order", None)
            normalized_column.setdefault("visible", None)
            normalized_column.setdefault("width", None)
            normalized_column.setdefault("fixed", None)
            normalized_columns.append(normalized_column)
        canonical["columns"] = normalized_columns
    return canonical


def _config_hash(config: dict[str, Any]) -> str:
    canonical_json = json.dumps(
        _canonical_config(config),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _origin_table(connection: sa.Connection, *, create: bool) -> sa.Table | None:
    metadata = sa.MetaData()
    table = sa.Table(
        _ORIGIN_TABLE_NAME,
        metadata,
        sa.Column("preference_id", sa.BigInteger, primary_key=True),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("original_config_json", sa.Text, nullable=False),
        sa.Column("migrated_config_hash", sa.String(64), nullable=False),
    )
    if create:
        table.create(connection, checkfirst=True)
        return table
    if not sa.inspect(connection).has_table(_ORIGIN_TABLE_NAME):
        return None
    return sa.Table(_ORIGIN_TABLE_NAME, sa.MetaData(), autoload_with=connection)


def _record_origin(
    connection: sa.Connection,
    origin_table: sa.Table,
    *,
    preference_id: Any,
    origin: str,
    original_config_json: str,
    migrated_config: dict[str, Any],
) -> None:
    existing = connection.execute(
        sa.select(origin_table.c.preference_id).where(
            origin_table.c.preference_id == preference_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    connection.execute(
        origin_table.insert().values(
            preference_id=preference_id,
            origin=origin,
            original_config_json=original_config_json,
            migrated_config_hash=_config_hash(migrated_config),
        )
    )


def _owner_match(
    table: sa.Table, row: sa.RowMapping, view_key: str
) -> sa.ColumnElement[bool]:
    clauses = [table.c.view_key == view_key]
    clauses.extend(table.c[column] == row[column] for column in _OWNER_KEY_COLUMNS)
    return sa.and_(*clauses)


def upgrade() -> None:
    connection = op.get_bind()
    origin_table = _origin_table(connection, create=True)
    assert origin_table is not None

    table = _load_table(connection)
    if table is None:
        return

    sources = connection.execute(
        sa.select(table).where(table.c.view_key == _LEGACY_VIEW_KEY).order_by(table.c.id)
    ).mappings().all()

    for source in sources:
        target = connection.execute(
            sa.select(table).where(_owner_match(table, source, _TARGET_VIEW_KEY))
        ).mappings().first()
        if target is not None and target["id"] != source["id"]:
            target_config = _parse_config(target["config_json"])
            if target_config is not None and "display_mode" not in target_config:
                migrated_config = dict(target_config)
                migrated_config["display_mode"] = "board"
                connection.execute(
                    table.update()
                    .where(table.c.id == target["id"])
                    .values(config_json=_serialize_config(migrated_config))
                )
                _record_origin(
                    connection,
                    origin_table,
                    preference_id=target["id"],
                    origin=_COLLISION_ORIGIN,
                    original_config_json=target["config_json"],
                    migrated_config=migrated_config,
                )
            connection.execute(table.delete().where(table.c.id == source["id"]))
            continue

        source_config = _parse_config(source["config_json"])
        if source_config is None:
            source_config = {"version": 1, "columns": []}
        migrated_config = dict(source_config)
        migrated_config["display_mode"] = "board"
        connection.execute(
            table.update()
            .where(table.c.id == source["id"])
            .values(
                view_key=_TARGET_VIEW_KEY,
                config_json=_serialize_config(migrated_config),
            )
        )
        _record_origin(
            connection,
            origin_table,
            preference_id=source["id"],
            origin=_RENAMED_ORIGIN,
            original_config_json=source["config_json"],
            migrated_config=migrated_config,
        )


def downgrade() -> None:
    connection = op.get_bind()
    origin_table = _origin_table(connection, create=False)
    if origin_table is None:
        return

    table = _load_table(connection)
    if table is not None:
        origins = connection.execute(
            sa.select(origin_table).order_by(origin_table.c.preference_id)
        ).mappings().all()
        for origin_row in origins:
            target = connection.execute(
                sa.select(table).where(
                    table.c.id == origin_row["preference_id"],
                    table.c.view_key == _TARGET_VIEW_KEY,
                )
            ).mappings().first()
            if target is None:
                continue

            current_config = _parse_config(target["config_json"])
            if (
                current_config is None
                or current_config.get("display_mode") != "board"
                or _config_hash(current_config) != origin_row["migrated_config_hash"]
            ):
                continue

            if origin_row["origin"] == _COLLISION_ORIGIN:
                connection.execute(
                    table.update()
                    .where(table.c.id == target["id"])
                    .values(config_json=origin_row["original_config_json"])
                )
                continue

            if origin_row["origin"] != _RENAMED_ORIGIN:
                continue
            legacy_exists = connection.execute(
                sa.select(table.c.id)
                .where(_owner_match(table, target, _LEGACY_VIEW_KEY))
                .limit(1)
            ).scalar_one_or_none()
            values: dict[str, Any] = {
                "config_json": origin_row["original_config_json"]
            }
            if legacy_exists is None:
                values["view_key"] = _LEGACY_VIEW_KEY
            connection.execute(
                table.update().where(table.c.id == target["id"]).values(**values)
            )

    origin_table.drop(connection, checkfirst=True)
