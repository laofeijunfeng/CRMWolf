"""add customer brief fields

Revision ID: 026_customer_brief_fields
Revises: 025_repair_score_system_tables
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "026_customer_brief_fields"
down_revision: Union[str, None] = "025_repair_score_system_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def upgrade() -> None:
    columns = [
        ("customer_brief_json", sa.Column("customer_brief_json", sa.Text(), nullable=True, comment="客户概况结构化内容（JSON格式，AI生成）")),
        ("customer_brief_markdown", sa.Column("customer_brief_markdown", sa.Text(), nullable=True, comment="客户概况 Markdown 内容（AI生成）")),
        ("customer_brief_citations", sa.Column("customer_brief_citations", sa.Text(), nullable=True, comment="客户概况引用来源映射（JSON格式）")),
        ("customer_brief_status", sa.Column("customer_brief_status", sa.String(20), nullable=True, server_default="PENDING", comment="客户概况生成状态：PENDING/GENERATING/COMPLETED/FAILED")),
        ("customer_brief_generated_time", sa.Column("customer_brief_generated_time", sa.DateTime(), nullable=True, comment="客户概况生成完成时间")),
        ("customer_brief_error_message", sa.Column("customer_brief_error_message", sa.Text(), nullable=True, comment="客户概况生成失败原因")),
    ]

    for column_name, column in columns:
        if not _column_exists("crm_customers", column_name):
            op.add_column("crm_customers", column)


def downgrade() -> None:
    for column_name in [
        "customer_brief_error_message",
        "customer_brief_generated_time",
        "customer_brief_status",
        "customer_brief_citations",
        "customer_brief_markdown",
        "customer_brief_json",
    ]:
        if _column_exists("crm_customers", column_name):
            op.drop_column("crm_customers", column_name)
