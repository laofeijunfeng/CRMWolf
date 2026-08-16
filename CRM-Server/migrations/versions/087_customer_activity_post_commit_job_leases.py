"""add execution leases to customer activity post-commit jobs

Revision ID: 087_customer_activity_post_commit_job_leases
Revises: 086_im_confirmation_delivery_binding
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "087_customer_activity_post_commit_job_leases"
down_revision: str | None = "086_im_confirmation_delivery_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_customer_activity_post_commit_jobs"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("lease_token", sa.String(length=64), nullable=True, comment="当前执行租约令牌"))
    op.add_column(TABLE, sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="当前执行租约过期时间"))
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_lease_token"), TABLE, ["lease_token"])
    op.create_index(op.f("ix_crm_customer_activity_post_commit_jobs_lease_expires_at"), TABLE, ["lease_expires_at"])
    op.drop_index("idx_customer_activity_post_commit_recovery", table_name=TABLE)
    op.create_index(
        "idx_customer_activity_post_commit_recovery",
        TABLE,
        ["status", "next_attempt_at", "lease_expires_at", "attempt_count", "created_time"],
    )


def downgrade() -> None:
    op.drop_index("idx_customer_activity_post_commit_recovery", table_name=TABLE)
    op.create_index(
        "idx_customer_activity_post_commit_recovery",
        TABLE,
        ["status", "next_attempt_at", "attempt_count", "created_time"],
    )
    op.drop_index(op.f("ix_crm_customer_activity_post_commit_jobs_lease_expires_at"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_activity_post_commit_jobs_lease_token"), table_name=TABLE)
    op.drop_column(TABLE, "lease_expires_at")
    op.drop_column(TABLE, "lease_token")
