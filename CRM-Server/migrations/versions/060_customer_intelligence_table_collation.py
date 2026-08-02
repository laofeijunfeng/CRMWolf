"""align customer intelligence table collations

Revision ID: 060_customer_intelligence_table_collation
Revises: 059_license_application_authorized_users
Create Date: 2026-08-02

"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text


revision: str = "060_customer_intelligence_table_collation"
down_revision: str | None = "059_license_application_authorized_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CUSTOMER_INTELLIGENCE_TABLES = (
    "crm_customer_vector_documents",
    "crm_agent_memory_entries",
    "crm_customer_facts",
    "crm_customer_fact_sources",
    "crm_customer_fact_revisions",
    "crm_customer_fact_review_audits",
    "crm_customer_intelligence_runs",
)


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


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "mysql":
        return

    for table_name in CUSTOMER_INTELLIGENCE_TABLES:
        if _table_exists(table_name):
            op.execute(f"ALTER TABLE {table_name} CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "mysql":
        return

    for table_name in CUSTOMER_INTELLIGENCE_TABLES:
        if _table_exists(table_name):
            op.execute(f"ALTER TABLE {table_name} CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
