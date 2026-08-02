"""customer vector documents

Revision ID: 055_customer_vector_documents
Revises: 054_view_preference_sort_order
Create Date: 2026-08-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "055_customer_vector_documents"
down_revision: str | None = "054_view_preference_sort_order"
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
    if _table_exists("crm_customer_vector_documents"):
        return

    op.create_table(
        "crm_customer_vector_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("document_key", sa.String(length=64), nullable=False, comment="证据文档幂等键"),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="租户ID，当前与团队ID一致"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("source_type", sa.String(length=50), nullable=False, comment="来源类型"),
        sa.Column("source_object_id", sa.String(length=100), nullable=False, comment="来源对象ID"),
        sa.Column("business_object_type", sa.String(length=50), nullable=True, comment="业务对象类型"),
        sa.Column("business_object_id", sa.String(length=100), nullable=True, comment="业务对象ID"),
        sa.Column("title", sa.String(length=255), nullable=False, comment="证据标题"),
        sa.Column("text", sa.Text(), nullable=False, comment="可检索证据文本"),
        sa.Column("text_hash", sa.String(length=64), nullable=False, comment="证据文本SHA256"),
        sa.Column("qdrant_point_id", sa.String(length=64), nullable=False, comment="Qdrant point ID"),
        sa.Column("occurred_at", sa.DateTime(), nullable=True, comment="业务发生时间"),
        sa.Column("confidence", sa.Float(), nullable=True, comment="证据置信度"),
        sa.Column("visibility_scope", sa.String(length=30), nullable=False, server_default="team", comment="可见范围"),
        sa.Column("metadata_version", sa.BigInteger(), nullable=False, server_default="1", comment="元数据版本"),
        sa.Column("sync_status", sa.String(length=20), nullable=False, server_default="PENDING", comment="向量同步状态"),
        sa.Column("sync_error", sa.Text(), nullable=True, comment="向量同步失败原因"),
        sa.Column("synced_at", sa.DateTime(), nullable=True, comment="向量同步时间"),
        sa.Column("created_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_key"),
        sa.UniqueConstraint("qdrant_point_id"),
        sa.UniqueConstraint("team_id", "source_type", "source_object_id", name="uq_customer_vector_source"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="客户智能档案向量证据元数据表",
    )
    op.create_index("ix_crm_customer_vector_documents_customer_id", "crm_customer_vector_documents", ["customer_id"])
    op.create_index("ix_crm_customer_vector_documents_document_key", "crm_customer_vector_documents", ["document_key"])
    op.create_index("ix_crm_customer_vector_documents_occurred_at", "crm_customer_vector_documents", ["occurred_at"])
    op.create_index("ix_crm_customer_vector_documents_source_type", "crm_customer_vector_documents", ["source_type"])
    op.create_index("ix_crm_customer_vector_documents_sync_status", "crm_customer_vector_documents", ["sync_status"])
    op.create_index("ix_crm_customer_vector_documents_team_id", "crm_customer_vector_documents", ["team_id"])
    op.create_index("ix_crm_customer_vector_documents_tenant_id", "crm_customer_vector_documents", ["tenant_id"])
    op.create_index("idx_customer_vector_customer_status", "crm_customer_vector_documents", ["customer_id", "sync_status"])
    op.create_index("idx_customer_vector_team_customer_time", "crm_customer_vector_documents", ["team_id", "customer_id", "occurred_at"])


def downgrade() -> None:
    if _table_exists("crm_customer_vector_documents"):
        op.drop_table("crm_customer_vector_documents")
