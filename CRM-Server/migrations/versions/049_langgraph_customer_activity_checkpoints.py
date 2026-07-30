"""langgraph customer activity checkpoints

Revision ID: 049_langgraph_customer_activity_checkpoints
Revises: 048_customer_activities
Create Date: 2026-07-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import mysql


revision: str = "049_langgraph_customer_activity_checkpoints"
down_revision: str | None = "048_customer_activities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def upgrade() -> None:
    if not _table_exists("crm_langgraph_checkpoints"):
        op.create_table(
            "crm_langgraph_checkpoints",
            sa.Column("thread_id", sa.String(length=191), nullable=False),
            sa.Column("checkpoint_ns", sa.String(length=191), nullable=False, server_default=""),
            sa.Column("checkpoint_id", sa.String(length=191), nullable=False),
            sa.Column("parent_checkpoint_id", sa.String(length=191), nullable=True),
            sa.Column("checkpoint_type", sa.String(length=100), nullable=False),
            sa.Column("checkpoint_blob", mysql.LONGBLOB(), nullable=False),
            sa.Column("metadata_type", sa.String(length=100), nullable=False),
            sa.Column("metadata_blob", mysql.LONGBLOB(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_langgraph_checkpoints_thread", "crm_langgraph_checkpoints", ["thread_id"])

    if not _table_exists("crm_langgraph_checkpoint_blobs"):
        op.create_table(
            "crm_langgraph_checkpoint_blobs",
            sa.Column("thread_id", sa.String(length=191), nullable=False),
            sa.Column("checkpoint_ns", sa.String(length=191), nullable=False, server_default=""),
            sa.Column("channel", sa.String(length=191), nullable=False),
            sa.Column("version", sa.String(length=191), nullable=False),
            sa.Column("serde_type", sa.String(length=100), nullable=False),
            sa.Column("blob", mysql.LONGBLOB(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "channel", "version"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_langgraph_checkpoint_blobs_thread", "crm_langgraph_checkpoint_blobs", ["thread_id"])

    if not _table_exists("crm_langgraph_checkpoint_writes"):
        op.create_table(
            "crm_langgraph_checkpoint_writes",
            sa.Column("thread_id", sa.String(length=191), nullable=False),
            sa.Column("checkpoint_ns", sa.String(length=191), nullable=False, server_default=""),
            sa.Column("checkpoint_id", sa.String(length=191), nullable=False),
            sa.Column("task_id", sa.String(length=191), nullable=False),
            sa.Column("write_idx", sa.Integer(), nullable=False),
            sa.Column("task_path", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("channel", sa.String(length=191), nullable=False),
            sa.Column("serde_type", sa.String(length=100), nullable=False),
            sa.Column("blob", mysql.LONGBLOB(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "write_idx"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("idx_langgraph_checkpoint_writes_thread", "crm_langgraph_checkpoint_writes", ["thread_id"])


def downgrade() -> None:
    for table_name in (
        "crm_langgraph_checkpoint_writes",
        "crm_langgraph_checkpoint_blobs",
        "crm_langgraph_checkpoints",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
