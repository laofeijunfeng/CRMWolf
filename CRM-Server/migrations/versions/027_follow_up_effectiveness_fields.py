"""add follow up effectiveness fields

Revision ID: 027_follow_up_effectiveness_fields
Revises: 026_customer_brief_fields
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "027_follow_up_effectiveness_fields"
down_revision: Union[str, None] = "026_customer_brief_fields"
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
        ("effectiveness_score", sa.Column("effectiveness_score", sa.Integer(), nullable=True, comment="AI评估有效跟进得分，满分100")),
        ("effectiveness_is_valid", sa.Column("effectiveness_is_valid", sa.Boolean(), nullable=True, comment="AI评估是否有效")),
        ("effectiveness_reason", sa.Column("effectiveness_reason", sa.Text(), nullable=True, comment="AI评估原因摘要")),
        ("effectiveness_detail_json", sa.Column("effectiveness_detail_json", sa.Text(), nullable=True, comment="AI评估分项明细JSON")),
        ("effectiveness_status", sa.Column("effectiveness_status", sa.String(20), nullable=True, server_default="PENDING", comment="AI评估状态：PENDING/GENERATING/COMPLETED/FAILED")),
        ("effectiveness_evaluated_time", sa.Column("effectiveness_evaluated_time", sa.DateTime(), nullable=True, comment="AI评估完成时间")),
        ("effectiveness_error_message", sa.Column("effectiveness_error_message", sa.Text(), nullable=True, comment="AI评估失败原因")),
    ]

    for column_name, column in columns:
        if not _column_exists("crm_customer_follow_ups", column_name):
            op.add_column("crm_customer_follow_ups", column)


def downgrade() -> None:
    for column_name in [
        "effectiveness_error_message",
        "effectiveness_evaluated_time",
        "effectiveness_status",
        "effectiveness_detail_json",
        "effectiveness_reason",
        "effectiveness_is_valid",
        "effectiveness_score",
    ]:
        if _column_exists("crm_customer_follow_ups", column_name):
            op.drop_column("crm_customer_follow_ups", column_name)
