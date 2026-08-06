"""add cancellation audit fields to follow up task confirmation cases

Revision ID: 074_follow_up_task_confirmation_case_cancellation_fields
Revises: 073_follow_up_task_reconciliation_evaluation_runs
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "074_follow_up_task_confirmation_case_cancellation_fields"
down_revision: str | None = "073_follow_up_task_reconciliation_evaluation_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).all()
        return bool(rows)

    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
            """),
            {"table_name": table_name},
        ).scalar()
        > 0
    )


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).all()
        return any(row[1] == column_name for row in rows)

    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND column_name = :column_name
            """),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()
        > 0
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA index_list({table_name})")).all()
        return any(row[1] == index_name for row in rows)

    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND index_name = :index_name
            """),
            {"table_name": table_name, "index_name": index_name},
        ).scalar()
        > 0
    )


def upgrade() -> None:
    table_name = "crm_follow_up_task_confirmation_cases"
    if not _table_exists(table_name):
        return

    if not _column_exists(table_name, "cancelled_at"):
        op.add_column(table_name, sa.Column("cancelled_at", sa.DateTime(), nullable=True, comment="确认Case取消时间"))
    if not _column_exists(table_name, "cancelled_by_id"):
        op.add_column(
            table_name,
            sa.Column("cancelled_by_id", sa.String(length=100), nullable=True, comment="确认Case取消人"),
        )
    if not _index_exists(table_name, "idx_follow_up_confirmation_cancelled_by"):
        op.create_index("idx_follow_up_confirmation_cancelled_by", table_name, ["cancelled_by_id"])
    if not _column_exists(table_name, "cancelled_reason"):
        op.add_column(
            table_name,
            sa.Column("cancelled_reason", sa.String(length=80), nullable=True, comment="确认Case取消原因"),
        )
    if not _index_exists(table_name, "idx_follow_up_confirmation_cancelled_reason"):
        op.create_index("idx_follow_up_confirmation_cancelled_reason", table_name, ["cancelled_reason"])


def downgrade() -> None:
    table_name = "crm_follow_up_task_confirmation_cases"
    if not _table_exists(table_name):
        return

    if _column_exists(table_name, "cancelled_reason"):
        if _index_exists(table_name, "idx_follow_up_confirmation_cancelled_reason"):
            op.drop_index("idx_follow_up_confirmation_cancelled_reason", table_name=table_name)
        op.drop_column(table_name, "cancelled_reason")
    if _column_exists(table_name, "cancelled_by_id"):
        if _index_exists(table_name, "idx_follow_up_confirmation_cancelled_by"):
            op.drop_index("idx_follow_up_confirmation_cancelled_by", table_name=table_name)
        op.drop_column(table_name, "cancelled_by_id")
    if _column_exists(table_name, "cancelled_at"):
        op.drop_column(table_name, "cancelled_at")
