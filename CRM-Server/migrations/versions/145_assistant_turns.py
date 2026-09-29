"""Durable, idempotent requests and lease-fenced turns for the 2.0 assistant.

Revision ID: 145_assistant_turns
Revises: 144_assistant2_activity_source
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "145_assistant_turns"
down_revision: str | None = "144_assistant2_activity_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crm_assistant_tasks", sa.Column("active_turn_id", sa.BigInteger(), nullable=True))
    op.create_table(
        "crm_assistant_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("client_request_id", sa.String(128), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crm_assistant_tasks.id"), nullable=False),
        sa.Column("turn_id", sa.BigInteger(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("team_id", "user_id", "client_request_id", name="uq_assistant_request_owner_key"),
    )
    op.create_table(
        "crm_assistant_turns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crm_assistant_tasks.id"), nullable=False),
        sa.Column("request_id", sa.BigInteger(), sa.ForeignKey("crm_assistant_requests.id"), nullable=False, unique=True),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_version", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_seq", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.Column("last_modified_time", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_assistant_turn_recover", "crm_assistant_turns", ["status", "lease_expires_at", "id"])
    op.create_index("idx_assistant_turn_task", "crm_assistant_turns", ["team_id", "task_id", "id"])
    op.create_table(
        "crm_assistant_turn_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("turn_id", sa.BigInteger(), sa.ForeignKey("crm_assistant_turns.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("turn_id", "seq", name="uq_assistant_turn_event_sequence"),
    )


def downgrade() -> None:
    op.drop_table("crm_assistant_turn_events")
    op.drop_index("idx_assistant_turn_task", table_name="crm_assistant_turns")
    op.drop_index("idx_assistant_turn_recover", table_name="crm_assistant_turns")
    op.drop_table("crm_assistant_turns")
    op.drop_table("crm_assistant_requests")
    op.drop_column("crm_assistant_tasks", "active_turn_id")
