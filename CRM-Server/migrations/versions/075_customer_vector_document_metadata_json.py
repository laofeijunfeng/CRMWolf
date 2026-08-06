"""add metadata json to customer vector documents

Revision ID: 075_customer_vector_document_metadata_json
Revises: 074_follow_up_task_confirmation_case_cancellation_fields
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "075_customer_vector_document_metadata_json"
down_revision: str | None = "074_follow_up_task_confirmation_case_cancellation_fields"
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


def upgrade() -> None:
    table_name = "crm_customer_vector_documents"
    if not _table_exists(table_name):
        return
    if not _column_exists(table_name, "metadata_json"):
        op.add_column(table_name, sa.Column("metadata_json", sa.JSON(), nullable=True, comment="向量证据业务元数据"))


def downgrade() -> None:
    table_name = "crm_customer_vector_documents"
    if not _table_exists(table_name):
        return
    if _column_exists(table_name, "metadata_json"):
        op.drop_column(table_name, "metadata_json")
