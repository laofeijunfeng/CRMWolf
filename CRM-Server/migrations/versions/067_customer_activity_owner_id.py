"""add owner id to customer activities

Revision ID: 067_customer_activity_owner_id
Revises: 066_opportunity_public_ids
Create Date: 2026-08-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "067_customer_activity_owner_id"
down_revision: str | None = "066_opportunity_public_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "crm_customer_activities"


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return any(row["name"] == column_name for row in rows)

    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA index_list({table_name})")).mappings().all()
        return any(row["name"] == index_name for row in rows)

    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
          AND index_name = :index_name
    """), {"table_name": table_name, "index_name": index_name}).scalar() > 0


def _create_index_if_missing(index_name: str, columns: list[str]) -> None:
    if not _index_exists(TABLE_NAME, index_name):
        op.create_index(index_name, TABLE_NAME, columns)


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(TABLE_NAME, "owner_id"):
        op.add_column(
            TABLE_NAME,
            sa.Column("owner_id", sa.String(length=100), nullable=True, comment="跟进归属人"),
        )

    conn.execute(text(f"""
        UPDATE {TABLE_NAME}
        SET owner_id = creator_id
        WHERE owner_id IS NULL OR owner_id = ''
    """))

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.alter_column(
            "owner_id",
            existing_type=sa.String(length=100),
            nullable=False,
            existing_comment="跟进归属人",
        )

    _create_index_if_missing("idx_customer_activity_owner", ["owner_id"])
    _create_index_if_missing("idx_customer_activity_team_owner_occurred", ["team_id", "owner_id", "occurred_at"])


def downgrade() -> None:
    if _index_exists(TABLE_NAME, "idx_customer_activity_team_owner_occurred"):
        op.drop_index("idx_customer_activity_team_owner_occurred", table_name=TABLE_NAME)
    if _index_exists(TABLE_NAME, "idx_customer_activity_owner"):
        op.drop_index("idx_customer_activity_owner", table_name=TABLE_NAME)
    if _column_exists(TABLE_NAME, "owner_id"):
        op.drop_column(TABLE_NAME, "owner_id")
