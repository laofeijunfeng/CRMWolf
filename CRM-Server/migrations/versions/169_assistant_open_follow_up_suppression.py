"""Add weekly suppression for Assistant open follow-up disposition cards.

Revision ID: 169_follow_up_week_suppression
Revises: 168_repair_approval_participants
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "169_follow_up_week_suppression"
down_revision: str | None = "168_repair_approval_participants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_assistant_open_follow_up_suppressions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False,
                  comment="主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("week_start", sa.Date(), nullable=False, comment="Asia/Shanghai 周一"),
        sa.Column(
            "created_time",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_time",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["crm_customers.id"],
            name="fk_assistant_open_follow_up_suppressions_customer",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "customer_id",
            "week_start",
            name="uq_assistant_open_follow_up_suppression_week",
        ),
        comment="销售助手历史跟进任务按客户自然周抑制",
    )
    op.create_index(
        "ix_crm_assistant_open_follow_up_suppressions_customer_id",
        "crm_assistant_open_follow_up_suppressions",
        ["customer_id"],
    )


def downgrade() -> None:
    op.drop_table("crm_assistant_open_follow_up_suppressions")
