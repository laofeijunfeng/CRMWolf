"""assistant continuous conversations

Revision ID: 02352b41bcb6
Revises: 153_remove_customer_profile_complete
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "02352b41bcb6"
down_revision: str | None = "153_remove_customer_profile_complete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONVERSATION_TABLE = "crm_assistant_conversations"
_ENTRY_TABLE = "crm_assistant_conversation_entries"
_CURRENT_COLUMNS = {
    "id",
    "public_id",
    "team_id",
    "user_id",
    "version",
    "focused_task_public_id",
    "pending_choice_id",
    "busy_entry_id",
    "lease_expires_at",
    "created_time",
}
_LEGACY_COLUMNS = {
    "id",
    "public_id",
    "team_id",
    "user_id",
    "created_time",
    "last_modified_time",
    "next_message_seq",
}


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table_name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _ensure_entry_table() -> None:
    if _table_exists(_ENTRY_TABLE):
        missing = _CURRENT_ENTRY_COLUMNS - _columns(_ENTRY_TABLE)
        if missing:
            raise RuntimeError("assistant conversation entries table is missing columns: " + ", ".join(sorted(missing)))
        return
    op.create_table(
        _ENTRY_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "conversation_id",
            sa.BigInteger(),
            sa.ForeignKey(
                f"{_CONVERSATION_TABLE}.id",
                name="fk_assistant_entry_conversation",
            ),
            nullable=False,
        ),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("client_request_id", sa.String(128), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=False),
        sa.Column("command_json", sa.JSON(), nullable=False),
        sa.Column("decision_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("task_public_id", sa.String(64), nullable=True),
        sa.Column("turn_public_id", sa.String(64), nullable=True),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("task_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "conversation_id",
            "client_request_id",
            name="uq_assistant_conversation_request",
        ),
    )
    op.create_index(
        "idx_assistant_conversation_page",
        _ENTRY_TABLE,
        ["team_id", "user_id", "conversation_id", "id"],
    )


_CURRENT_ENTRY_COLUMNS = {
    "id",
    "public_id",
    "conversation_id",
    "team_id",
    "user_id",
    "client_request_id",
    "input_fingerprint",
    "user_text",
    "command_json",
    "decision_json",
    "state",
    "task_public_id",
    "turn_public_id",
    "reply_text",
    "task_snapshot_json",
    "created_time",
}


def upgrade() -> None:
    if _table_exists(_CONVERSATION_TABLE):
        columns = _columns(_CONVERSATION_TABLE)
        if "version" not in columns and "last_modified_time" in columns:
            # The recovered 154-156 path owns this table, including a partial
            # 154 shape that does not yet have next_message_seq. Revision 157
            # performs the non-destructive archive bridge.
            return
        if not columns >= _CURRENT_COLUMNS:
            raise RuntimeError("assistant conversation table is neither the recovered schema nor the current schema")
        _ensure_entry_table()
        return

    if _table_exists(_ENTRY_TABLE):
        raise RuntimeError("assistant conversation entries exist without their parent conversation table")

    op.create_table(
        _CONVERSATION_TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("focused_task_public_id", sa.String(64), nullable=True),
        sa.Column("pending_choice_id", sa.String(64), nullable=True),
        sa.Column("busy_entry_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("team_id", "user_id", name="uq_assistant_conversation_owner"),
    )
    _ensure_entry_table()


def downgrade() -> None:
    if not _table_exists(_CONVERSATION_TABLE):
        return
    columns = _columns(_CONVERSATION_TABLE)
    if not columns >= _CURRENT_COLUMNS or columns >= _LEGACY_COLUMNS:
        return
    if _table_exists(_ENTRY_TABLE):
        op.drop_index("idx_assistant_conversation_page", table_name=_ENTRY_TABLE)
        op.drop_table(_ENTRY_TABLE)
    op.drop_table(_CONVERSATION_TABLE)
