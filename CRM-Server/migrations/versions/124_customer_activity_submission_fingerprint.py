"""Add request fingerprint for customer activity submission replay."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "124_customer_activity_submission_fingerprint"
down_revision: str | None = "123_payment_record_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_customer_activities",
        sa.Column("submission_fingerprint", sa.String(length=64), nullable=True, comment="页面提交请求指纹"),
    )


def downgrade() -> None:
    op.drop_column("crm_customer_activities", "submission_fingerprint")
