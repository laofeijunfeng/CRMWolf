"""Migrate persisted Agent entity lists to authoritative EntityRef items.

Revision ID: 103_migrate_agent_entity_list_items
Revises: 102_drop_agent_task_compatibility
Create Date: 2026-08-24
"""

from collections.abc import Sequence
from copy import deepcopy

import sqlalchemy as sa
from alembic import op

revision: str = "103_migrate_agent_entity_list_items"
down_revision: str | None = "102_drop_agent_task_compatibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MESSAGE_TABLE = "crm_agent_messages"
RESULT_SET_TABLE = "crm_agent_query_result_sets"
ACTION_TABLE = "crm_agent_ui_actions"


def upgrade() -> None:
    connection = op.get_bind()
    messages = sa.table(
        MESSAGE_TABLE,
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("session_id", sa.BigInteger()),
        sa.column("ui_json", sa.JSON()),
        sa.column("last_modified_time", sa.DateTime()),
    )
    result_sets = sa.table(
        RESULT_SET_TABLE,
        sa.column("public_id", sa.String()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("user_id", sa.BigInteger()),
        sa.column("session_id", sa.BigInteger()),
        sa.column("source_message_id", sa.BigInteger()),
        sa.column("resource", sa.String()),
        sa.column("ordered_entity_refs_json", sa.JSON()),
    )
    actions = sa.table(
        ACTION_TABLE,
        sa.column("public_id", sa.String()),
        sa.column("message_id", sa.BigInteger()),
        sa.column("status", sa.String()),
        sa.column("last_modified_time", sa.DateTime()),
    )

    rows = connection.execute(
        sa.select(
            messages.c.id,
            messages.c.team_id,
            messages.c.user_id,
            messages.c.session_id,
            messages.c.ui_json,
        ).where(messages.c.ui_json.is_not(None))
    ).mappings()
    for row in rows:
        migrated, revoked_action_ids = _migrate_envelope(
            connection,
            result_sets,
            message_id=int(row["id"]),
            team_id=int(row["team_id"]),
            user_id=int(row["user_id"]),
            session_id=int(row["session_id"]),
            ui_json=row["ui_json"],
        )
        if migrated is None:
            continue
        connection.execute(
            sa.update(messages)
            .where(messages.c.id == row["id"])
            .values(ui_json=migrated, last_modified_time=sa.func.now())
        )
        if revoked_action_ids:
            connection.execute(
                sa.update(actions)
                .where(
                    actions.c.message_id == row["id"],
                    actions.c.public_id.in_(revoked_action_ids),
                    actions.c.status.in_(("ACTIVE", "CONSUMING")),
                )
                .values(status="REVOKED", last_modified_time=sa.func.now())
            )


def downgrade() -> None:
    raise RuntimeError("Agent entity-list contract migration is intentionally irreversible")


def _migrate_envelope(
    connection: sa.Connection,
    result_sets: sa.TableClause,
    *,
    message_id: int,
    team_id: int,
    user_id: int,
    session_id: int,
    ui_json: object,
) -> tuple[dict[str, object] | None, set[str]]:
    if not isinstance(ui_json, dict) or not isinstance(ui_json.get("blocks"), list):
        return None, set()
    envelope = deepcopy(ui_json)
    migrated = False
    revoked_action_ids: set[str] = set()
    current_blocks: list[object] = []
    for block in envelope["blocks"]:
        if not _is_legacy_entity_list(block):
            current_blocks.append(block)
            continue
        migrated = True
        for item in block["items"]:
            if isinstance(item, dict) and isinstance(item.get("actions"), list):
                revoked_action_ids.update(
                    action["action_id"]
                    for action in item["actions"]
                    if isinstance(action, dict) and isinstance(action.get("action_id"), str)
                )
        refs = _authoritative_refs(
            connection,
            result_sets,
            message_id=message_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            block=block,
        )
        if refs is None:
            # Resources without server-issued EntityRefs are text-only in the
            # current contract; retaining a synthetic clickable row would be unsafe.
            continue
        block["items"] = [{"entity_ref": ref} for ref in refs]
        current_blocks.append(block)
    if not migrated:
        return None, set()
    envelope["blocks"] = current_blocks
    return envelope, revoked_action_ids


def _is_legacy_entity_list(block: object) -> bool:
    if not isinstance(block, dict) or block.get("type") != "entity_list":
        return False
    items = block.get("items")
    return isinstance(items, list) and any(isinstance(item, dict) and "entity_ref" not in item for item in items)


def _authoritative_refs(
    connection: sa.Connection,
    result_sets: sa.TableClause,
    *,
    message_id: int,
    team_id: int,
    user_id: int,
    session_id: int,
    block: dict[str, object],
) -> list[dict[str, object]] | None:
    result_set_id = block.get("result_set_id")
    resource = block.get("entity_type")
    items = block.get("items")
    if not isinstance(result_set_id, str) or not isinstance(resource, str) or not isinstance(items, list):
        raise RuntimeError(f"message {message_id} has an invalid legacy entity list")
    row = (
        connection.execute(
            sa.select(result_sets.c.resource, result_sets.c.ordered_entity_refs_json).where(
                result_sets.c.public_id == result_set_id,
                result_sets.c.team_id == team_id,
                result_sets.c.user_id == user_id,
                result_sets.c.session_id == session_id,
                result_sets.c.source_message_id == message_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(f"message {message_id} has no authoritative result set")
    refs = row["ordered_entity_refs_json"]
    if row["resource"] != resource:
        raise RuntimeError(f"message {message_id} result-set resource mismatch")
    if not isinstance(refs, list) or not refs:
        return None
    if len(refs) != len(items):
        raise RuntimeError(f"message {message_id} entity-list cardinality mismatch")
    required_keys = {"ref_id", "resource", "public_id", "display_name", "result_set_id"}
    for item, ref in zip(items, refs, strict=True):
        if not isinstance(item, dict) or not isinstance(ref, dict) or set(ref) != required_keys:
            raise RuntimeError(f"message {message_id} has invalid authoritative entity references")
        if (
            item.get("ref_id") != ref["ref_id"]
            or item.get("title") != ref["display_name"]
            or ref["resource"] != resource
            or ref["result_set_id"] != result_set_id
        ):
            raise RuntimeError(f"message {message_id} entity-list identity mismatch")
    return refs
