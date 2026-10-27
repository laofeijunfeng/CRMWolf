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


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _ensure_conversation_table() -> None:
    if _table_exists("crm_assistant_conversations"):
        return
    op.create_table(
        "crm_assistant_conversations",
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


def _ensure_entry_table() -> None:
    if not _table_exists("crm_assistant_conversation_entries"):
        op.create_table(
            "crm_assistant_conversation_entries",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("public_id", sa.String(64), nullable=False, unique=True),
            sa.Column(
                "conversation_id",
                sa.BigInteger(),
                sa.ForeignKey("crm_assistant_conversations.id"),
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
    if not _index_exists("crm_assistant_conversation_entries", "idx_assistant_conversation_page"):
        op.create_index(
            "idx_assistant_conversation_page",
            "crm_assistant_conversation_entries",
            ["team_id", "user_id", "conversation_id", "id"],
        )


def upgrade() -> None:
    _ensure_conversation_table()
    _ensure_entry_table()


def downgrade() -> None:
    op.drop_index("idx_assistant_conversation_page", table_name="crm_assistant_conversation_entries")
    op.drop_table("crm_assistant_conversation_entries")
    op.drop_table("crm_assistant_conversations")
