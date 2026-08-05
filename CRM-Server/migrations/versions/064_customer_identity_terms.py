"""customer identity terms

Revision ID: 064_customer_identity_terms
Revises: 063_customer_context_answer_telemetry
Create Date: 2026-08-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "064_customer_identity_terms"
down_revision: str | None = "063_customer_context_answer_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).all()
        return bool(rows)
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
    """), {"table_name": table_name}).scalar() > 0


def upgrade() -> None:
    if _table_exists("crm_customer_identity_terms"):
        return

    op.create_table(
        "crm_customer_identity_terms",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="租户ID，当前与团队ID一致"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("term", sa.String(length=255), nullable=False, comment="客户称呼、简称或匹配词"),
        sa.Column("normalized_term", sa.String(length=255), nullable=False, comment="归一化匹配词"),
        sa.Column("term_type", sa.String(length=50), nullable=False, comment="匹配词类型"),
        sa.Column("source", sa.String(length=50), nullable=False, comment="来源"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0", comment="置信度"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE", comment="状态"),
        sa.Column("conflict_group", sa.String(length=64), nullable=True, comment="冲突组"),
        sa.Column("evidence", sa.Text(), nullable=True, comment="生成或确认依据"),
        sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "customer_id", "normalized_term", "term_type", name="uq_customer_identity_term"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
        comment="客户身份解析匹配词表",
    )
    table_name = "crm_customer_identity_terms"
    op.create_index("ix_crm_customer_identity_terms_customer_id", table_name, ["customer_id"])
    op.create_index("ix_crm_customer_identity_terms_source", table_name, ["source"])
    op.create_index("ix_crm_customer_identity_terms_status", table_name, ["status"])
    op.create_index("ix_crm_customer_identity_terms_team_id", table_name, ["team_id"])
    op.create_index("ix_crm_customer_identity_terms_tenant_id", table_name, ["tenant_id"])
    op.create_index("ix_crm_customer_identity_terms_term_type", table_name, ["term_type"])
    op.create_index("ix_crm_customer_identity_terms_conflict_group", table_name, ["conflict_group"])
    op.create_index("idx_customer_identity_term_lookup", table_name, ["team_id", "normalized_term", "status"])
    op.create_index("idx_customer_identity_term_customer", table_name, ["team_id", "customer_id", "status"])


def downgrade() -> None:
    if _table_exists("crm_customer_identity_terms"):
        op.drop_table("crm_customer_identity_terms")
