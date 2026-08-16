"""add execution leases to follow up confirmation deliveries

Revision ID: 088_follow_up_confirmation_delivery_leases
Revises: 087_customer_activity_post_commit_job_leases
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "088_follow_up_confirmation_delivery_leases"
down_revision: str | None = "087_customer_activity_post_commit_job_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_follow_up_task_confirmation_prompt_deliveries"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("lease_token", sa.String(length=64), nullable=True, comment="当前投递租约令牌"))
    op.add_column(TABLE, sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="当前投递租约过期时间"))
    op.create_index(op.f("ix_crm_follow_up_task_confirmation_prompt_deliveries_lease_token"), TABLE, ["lease_token"])
    op.create_index(
        op.f("ix_crm_follow_up_task_confirmation_prompt_deliveries_lease_expires_at"), TABLE, ["lease_expires_at"]
    )
    op.drop_index("idx_follow_up_confirmation_recovery", table_name=TABLE)
    op.create_index(
        "idx_follow_up_confirmation_recovery",
        TABLE,
        ["status", "next_attempt_at", "lease_expires_at", "attempt_count", "created_time"],
    )


def downgrade() -> None:
    op.drop_index("idx_follow_up_confirmation_recovery", table_name=TABLE)
    op.create_index(
        "idx_follow_up_confirmation_recovery",
        TABLE,
        ["status", "next_attempt_at", "attempt_count", "created_time"],
    )
    op.drop_index(op.f("ix_crm_follow_up_task_confirmation_prompt_deliveries_lease_expires_at"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_follow_up_task_confirmation_prompt_deliveries_lease_token"), table_name=TABLE)
    op.drop_column(TABLE, "lease_expires_at")
    op.drop_column(TABLE, "lease_token")
