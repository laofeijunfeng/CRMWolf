"""Widen reminder run recipient ledger for per-recipient delivery.

Revision ID: 140_reminder_run_recipient_text
Revises: 139_reminder_rule_runs
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "140_reminder_run_recipient_text"
down_revision: str | None = "139_reminder_rule_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE = "crm_reminder_rule_runs"
COLUMN = "recipient_ids"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.alter_column(
            COLUMN,
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=False,
            existing_comment="接收用户ID",
        )


def downgrade() -> None:
    too_long = op.get_bind().execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE LENGTH({COLUMN}) > 500")
    ).scalar_one()
    if too_long:
        raise RuntimeError("Cannot shrink reminder recipient ledger: some values exceed 500 bytes")
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.alter_column(
            COLUMN,
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=False,
            existing_comment="接收用户ID",
        )
