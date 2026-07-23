"""customer members

Revision ID: 032_customer_members
Revises: 031_recalculate_payment_status_by_approved_records
Create Date: 2026-07-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "032_customer_members"
down_revision: Union[str, None] = "031_recalculate_payment_status_by_approved_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_customer_members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="成员系统用户ID"),
        sa.Column("member_role", sa.String(length=20), nullable=False, server_default="PRESALES", comment="成员角色"),
        sa.Column("access_level", sa.String(length=20), nullable=False, server_default="VIEW", comment="访问级别"),
        sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
        sa.Column("created_by", sa.String(length=100), nullable=False, comment="创建人"),
        sa.Column("created_time", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False, comment="更新时间"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False, comment="是否有效"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="客户团队成员表",
    )
    op.create_index("idx_customer_member_team", "crm_customer_members", ["team_id"])
    op.create_index("idx_customer_member_customer", "crm_customer_members", ["customer_id"])
    op.create_index("idx_customer_member_user", "crm_customer_members", ["user_id"])
    op.create_index(
        "idx_customer_member_team_customer_user_active",
        "crm_customer_members",
        ["team_id", "customer_id", "user_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("idx_customer_member_team_customer_user_active", table_name="crm_customer_members")
    op.drop_index("idx_customer_member_user", table_name="crm_customer_members")
    op.drop_index("idx_customer_member_customer", table_name="crm_customer_members")
    op.drop_index("idx_customer_member_team", table_name="crm_customer_members")
    op.drop_table("crm_customer_members")
