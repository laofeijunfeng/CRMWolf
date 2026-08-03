"""unify business numbers for approval entities

Revision ID: 061_unify_business_numbers
Revises: 060_customer_intelligence_table_collation
Create Date: 2026-08-03

"""
from collections.abc import Sequence
from datetime import date, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "061_unify_business_numbers"
down_revision: str | None = "060_customer_intelligence_table_collation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        return conn.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).scalar() > 0

    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


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


def _date_key(value) -> str:
    if value is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    try:
        return datetime.fromisoformat(str(value)).strftime("%Y%m%d")
    except ValueError:
        return date.today().strftime("%Y%m%d")


def _renumber_table(table_name: str, number_column: str, prefix: str) -> None:
    if not _table_exists(table_name) or not _column_exists(table_name, number_column):
        return

    conn = op.get_bind()
    rows = conn.execute(text(f"""
        SELECT id, created_time
        FROM {table_name}
        ORDER BY created_time ASC, id ASC
    """)).mappings().all()
    if not rows:
        return

    for row in rows:
        conn.execute(
            text(f"UPDATE {table_name} SET {number_column} = :number WHERE id = :id"),
            {"number": f"TMP-{prefix}-{row['id']}", "id": row["id"]},
        )

    sequence_by_date: dict[str, int] = {}
    for row in rows:
        day = _date_key(row["created_time"])
        sequence_by_date[day] = sequence_by_date.get(day, 0) + 1
        conn.execute(
            text(f"UPDATE {table_name} SET {number_column} = :number WHERE id = :id"),
            {"number": f"{prefix}{day}{sequence_by_date[day]:04d}", "id": row["id"]},
        )


def upgrade() -> None:
    conn = op.get_bind()

    if _table_exists("crm_opportunities") and not _column_exists("crm_opportunities", "opportunity_number"):
        op.add_column(
            "crm_opportunities",
            sa.Column("opportunity_number", sa.String(length=50), nullable=True, comment="商机编号（系统自动生成）"),
        )

    _renumber_table("crm_opportunities", "opportunity_number", "OPP")
    _renumber_table("crm_invoice_applications", "application_number", "INV")
    _renumber_table("crm_license_applications", "application_number", "LIC")

    if _table_exists("crm_opportunities") and _column_exists("crm_opportunities", "opportunity_number"):
        if conn.dialect.name != "sqlite":
            op.alter_column(
                "crm_opportunities",
                "opportunity_number",
                existing_type=sa.String(length=50),
                nullable=False,
                existing_comment="商机编号（系统自动生成）",
            )
        if not _index_exists("crm_opportunities", "ux_crm_opportunities_opportunity_number"):
            op.create_index(
                "ux_crm_opportunities_opportunity_number",
                "crm_opportunities",
                ["opportunity_number"],
                unique=True,
            )


def downgrade() -> None:
    if _table_exists("crm_opportunities"):
        if _index_exists("crm_opportunities", "ux_crm_opportunities_opportunity_number"):
            op.drop_index("ux_crm_opportunities_opportunity_number", table_name="crm_opportunities")
        if _column_exists("crm_opportunities", "opportunity_number"):
            op.drop_column("crm_opportunities", "opportunity_number")
