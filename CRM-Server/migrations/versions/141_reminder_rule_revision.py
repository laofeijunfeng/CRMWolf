"""Add stable revision tokens to reminder rules.

Revision ID: 141_reminder_rule_revision
Revises: 140_reminder_run_recipient_text
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "141_reminder_rule_revision"
down_revision: str | None = "140_reminder_run_recipient_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_reminder_rules",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1", comment="乐观锁修订号"),
    )


def downgrade() -> None:
    op.drop_column("crm_reminder_rules", "revision")
