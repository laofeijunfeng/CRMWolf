"""Keep hard-deleted customer activities observable to profile reconciliation.

Revision ID: 111_customer_activity_deletion_tombstones
Revises: 110_customer_profile_projection_tables
Create Date: 2026-08-29
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "111_customer_activity_deletion_tombstones"
down_revision: str | None = "110_customer_profile_projection_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_customer_activity_deletion_tombstones",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="删除水位主键"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("activity_id", sa.BigInteger(), nullable=False, comment="已删除客户活动ID"),
        sa.Column("deal_journey_id", sa.BigInteger(), nullable=True, comment="活动所属业务旅程ID快照"),
        sa.Column("activity_occurred_at", sa.DateTime(), nullable=True, comment="活动发生时间快照"),
        sa.Column("activity_revision", sa.Integer(), nullable=True, comment="删除前活动语义修订号"),
        sa.Column("deleted_at", sa.DateTime(), nullable=False, comment="删除时间"),
        sa.Column("deleted_by", sa.String(length=100), nullable=True, comment="删除人系统用户ID"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "activity_id", name="uq_customer_activity_deletion_tombstone"),
        comment="客户活动删除水位墓碑",
    )
    op.create_index(
        "idx_customer_activity_deletion_customer",
        "crm_customer_activity_deletion_tombstones",
        ["team_id", "customer_id", "id"],
    )
    op.create_index(
        "idx_customer_activity_deletion_time",
        "crm_customer_activity_deletion_tombstones",
        ["team_id", "customer_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_customer_activity_deletion_time",
        table_name="crm_customer_activity_deletion_tombstones",
    )
    op.drop_index(
        "idx_customer_activity_deletion_customer",
        table_name="crm_customer_activity_deletion_tombstones",
    )
    op.drop_table("crm_customer_activity_deletion_tombstones")
