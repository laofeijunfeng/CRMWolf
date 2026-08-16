"""add execution leases to customer intelligence runs

Revision ID: 089_customer_intelligence_run_leases
Revises: 088_follow_up_confirmation_delivery_leases
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "089_customer_intelligence_run_leases"
down_revision: str | None = "088_follow_up_confirmation_delivery_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_customer_intelligence_runs"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("lease_token", sa.String(length=64), nullable=True, comment="当前执行租约令牌"))
    op.add_column(TABLE, sa.Column("lease_expires_at", sa.DateTime(), nullable=True, comment="当前执行租约过期时间"))
    op.create_index(op.f("ix_crm_customer_intelligence_runs_lease_token"), TABLE, ["lease_token"])
    op.create_index(op.f("ix_crm_customer_intelligence_runs_lease_expires_at"), TABLE, ["lease_expires_at"])
    op.drop_index("idx_customer_intelligence_run_retry", table_name=TABLE)
    op.create_index(
        "idx_customer_intelligence_run_retry",
        TABLE,
        ["status", "next_retry_at", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_customer_intelligence_run_retry", table_name=TABLE)
    op.create_index("idx_customer_intelligence_run_retry", TABLE, ["status", "next_retry_at"])
    op.drop_index(op.f("ix_crm_customer_intelligence_runs_lease_expires_at"), table_name=TABLE)
    op.drop_index(op.f("ix_crm_customer_intelligence_runs_lease_token"), table_name=TABLE)
    op.drop_column(TABLE, "lease_expires_at")
    op.drop_column(TABLE, "lease_token")
