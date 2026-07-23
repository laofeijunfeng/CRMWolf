"""payment record commission member

Revision ID: 033_payment_record_commission_member
Revises: 032_customer_members
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "033_payment_record_commission_member"
down_revision: Union[str, None] = "032_customer_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(column_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND column_name = :column_name
    """), {"column_name": column_name}).scalar() > 0


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_payment_records'
        AND index_name = :index_name
    """), {"index_name": index_name}).scalar() > 0


def upgrade() -> None:
    if not _column_exists("commission_member_id"):
        op.add_column(
            "crm_payment_records",
            sa.Column("commission_member_id", sa.String(length=100), nullable=True, comment="提成协作成员系统用户ID"),
        )
    if not _column_exists("commission_member_name"):
        op.add_column(
            "crm_payment_records",
            sa.Column("commission_member_name", sa.String(length=100), nullable=True, comment="提成协作成员姓名"),
        )
    if not _index_exists("idx_payment_record_commission_member"):
        op.create_index(
            "idx_payment_record_commission_member",
            "crm_payment_records",
            ["team_id", "commission_member_id"],
        )


def downgrade() -> None:
    if _index_exists("idx_payment_record_commission_member"):
        op.drop_index("idx_payment_record_commission_member", table_name="crm_payment_records")
    if _column_exists("commission_member_name"):
        op.drop_column("crm_payment_records", "commission_member_name")
    if _column_exists("commission_member_id"):
        op.drop_column("crm_payment_records", "commission_member_id")
