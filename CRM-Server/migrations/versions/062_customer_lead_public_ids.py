"""add public ids for customers and leads

Revision ID: 062_customer_lead_public_ids
Revises: 061_unify_business_numbers
Create Date: 2026-08-03

"""
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "062_customer_lead_public_ids"
down_revision: str | None = "061_unify_business_numbers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def _add_and_backfill(table_name: str, prefix: str, index_name: str) -> None:
    conn = op.get_bind()

    if not _column_exists(table_name, "public_id"):
        op.add_column(
            table_name,
            sa.Column("public_id", sa.String(length=64), nullable=True, comment="对外ID"),
        )

    rows = conn.execute(text(f"""
        SELECT id
        FROM {table_name}
        WHERE public_id IS NULL OR public_id = ''
        ORDER BY id
    """)).mappings().all()

    for row in rows:
        conn.execute(
            text(f"UPDATE {table_name} SET public_id = :public_id WHERE id = :id"),
            {"public_id": f"{prefix}_{uuid4().hex}", "id": row["id"]},
        )

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            "public_id",
            existing_type=sa.String(length=64),
            nullable=False,
            existing_comment="对外ID",
        )

    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, ["public_id"], unique=True)


def _drop_public_id(table_name: str, index_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)
    if _column_exists(table_name, "public_id"):
        op.drop_column(table_name, "public_id")


def upgrade() -> None:
    _add_and_backfill("crm_customers", "cus", "uq_crm_customers_public_id")
    _add_and_backfill("crm_leads", "lead", "uq_crm_leads_public_id")


def downgrade() -> None:
    _drop_public_id("crm_leads", "uq_crm_leads_public_id")
    _drop_public_id("crm_customers", "uq_crm_customers_public_id")
