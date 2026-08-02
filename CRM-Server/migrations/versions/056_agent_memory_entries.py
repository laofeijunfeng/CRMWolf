"""agent memory entries

Revision ID: 056_agent_memory_entries
Revises: 055_customer_vector_documents
Create Date: 2026-08-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "056_agent_memory_entries"
down_revision: str | None = "055_customer_vector_documents"
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
    if _table_exists("crm_agent_memory_entries"):
        return

    op.create_table(
        "crm_agent_memory_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="租户ID，当前与团队ID一致"),
        sa.Column("namespace", sa.String(length=500), nullable=False, comment="LangGraph Store namespace"),
        sa.Column("key", sa.String(length=200), nullable=False, comment="namespace内记忆键"),
        sa.Column("value_json", sa.JSON(), nullable=False, comment="JSON可序列化记忆内容"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1", comment="记忆版本"),
        sa.Column("expires_at", sa.DateTime(), nullable=True, comment="过期时间"),
        sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("namespace", "key", name="uq_agent_memory_namespace_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="CRM AI Agent LangGraph长期记忆表",
    )
    op.create_index("ix_crm_agent_memory_entries_expires_at", "crm_agent_memory_entries", ["expires_at"])
    op.create_index("ix_crm_agent_memory_entries_namespace", "crm_agent_memory_entries", ["namespace"])
    op.create_index("ix_crm_agent_memory_entries_tenant_id", "crm_agent_memory_entries", ["tenant_id"])
    op.create_index("idx_agent_memory_tenant_namespace", "crm_agent_memory_entries", ["tenant_id", "namespace"])
    op.create_index("idx_agent_memory_namespace_updated", "crm_agent_memory_entries", ["namespace", "updated_time"])


def downgrade() -> None:
    if _table_exists("crm_agent_memory_entries"):
        op.drop_table("crm_agent_memory_entries")
