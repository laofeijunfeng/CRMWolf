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
_LEGACY_VIEW_KEY = "business-journey-board.board"
_TARGET_VIEW_KEY = "business-journeys.list"
_OWNER_KEY_COLUMNS = ("team_id", "scope", "user_id", "preference_key")
_MIGRATION_ORIGIN_KEY = "_migration_136_origin"
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


def _config_digest(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _add_origin_marker(config: dict[str, Any], origin: str, row_id: Any) -> None:
    config_digest = _config_digest(config)
    suffix = 0
    while True:
        marker_key = (
            _MIGRATION_ORIGIN_KEY
            if suffix == 0
            else f"{_MIGRATION_ORIGIN_KEY}_{suffix}"
        )
        if marker_key not in config:
            config[marker_key] = {
                "origin": origin,
                "row_id": row_id,
                "config_digest": config_digest,
            }
            return
        suffix += 1


def _pop_origin_marker(
    config: dict[str, Any], row_id: Any
) -> tuple[str, dict[str, Any]] | None:
    for marker_key, marker_value in config.items():
        if marker_key != _MIGRATION_ORIGIN_KEY and not marker_key.startswith(
            f"{_MIGRATION_ORIGIN_KEY}_"
        ):
            continue
        if not isinstance(marker_value, dict):
            continue
        origin = marker_value.get("origin")
        config_digest = marker_value.get("config_digest")
        if (
            marker_value.get("row_id") != row_id
            or origin not in {_RENAMED_ORIGIN, _COLLISION_ORIGIN}
            or not isinstance(config_digest, str)
        ):
            continue
        original_config = dict(config)
        original_config.pop(marker_key)
        original_config.pop("display_mode", None)
        if _config_digest(original_config) == config_digest:
            return origin, original_config
    return None


def _owner_match(table: sa.Table, row: sa.RowMapping) -> sa.ColumnElement[bool]:
    clauses = [table.c.view_key == _TARGET_VIEW_KEY]
    clauses.extend(table.c[column] == row[column] for column in _OWNER_KEY_COLUMNS)
    return sa.and_(*clauses)


def upgrade() -> None:
    connection = op.get_bind()
    table = _load_table(connection)
    if table is None:
        return

    sources = connection.execute(
        sa.select(table).where(table.c.view_key == _LEGACY_VIEW_KEY).order_by(table.c.id)
    ).mappings().all()

    for source in sources:
        target = connection.execute(sa.select(table).where(_owner_match(table, source))).mappings().first()
        if target is not None and target["id"] != source["id"]:
            target_config = _parse_config(target["config_json"])
            if target_config is not None and "display_mode" not in target_config:
                _add_origin_marker(target_config, _COLLISION_ORIGIN, target["id"])
                target_config["display_mode"] = "board"
                connection.execute(
                    table.update()
                    .where(table.c.id == target["id"])
                    .values(config_json=_serialize_config(target_config))
                )
            connection.execute(table.delete().where(table.c.id == source["id"]))
            continue

        source_config = _parse_config(source["config_json"])
        if source_config is None:
            source_config = {"version": 1, "columns": []}
        _add_origin_marker(source_config, _RENAMED_ORIGIN, source["id"])
        source_config["display_mode"] = "board"
        connection.execute(
            table.update()
            .where(table.c.id == source["id"])
            .values(
                view_key=_TARGET_VIEW_KEY,
                config_json=_serialize_config(source_config),
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    table = _load_table(connection)
    if table is None:
        return

    targets = connection.execute(
        sa.select(table).where(table.c.view_key == _TARGET_VIEW_KEY).order_by(table.c.id)
    ).mappings().all()

    for target in targets:
        config = _parse_config(target["config_json"])
        if config is None:
            continue
        marker = _pop_origin_marker(config, target["id"])
        if marker is None:
            continue
        origin, original_config = marker
        legacy_clauses = [table.c.view_key == _LEGACY_VIEW_KEY]
        legacy_clauses.extend(table.c[column] == target[column] for column in _OWNER_KEY_COLUMNS)
        legacy_exists = connection.execute(
            sa.select(table.c.id).where(sa.and_(*legacy_clauses)).limit(1)
        ).scalar_one_or_none()

        values: dict[str, Any] = {"config_json": _serialize_config(original_config)}
        if origin == _RENAMED_ORIGIN and legacy_exists is None:
            values["view_key"] = _LEGACY_VIEW_KEY
        connection.execute(table.update().where(table.c.id == target["id"]).values(**values))
