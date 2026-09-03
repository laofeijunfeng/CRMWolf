"""Add last-update timestamp for payment record final-state queries.

Revision ID: 124_payment_record_updated_time
Revises: 123_payment_record_idempotency
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "124_payment_record_updated_time"
down_revision: str | None = "123_payment_record_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_payment_records"
COLUMN = "updated_time"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            sa.DateTime(),
            nullable=True,
            comment="最后更新时间",
        ),
    )
    # Keep the migration compatible with existing rows and databases where the
    # application owns timestamp generation rather than relying on DB-specific
    # ON UPDATE syntax.
    op.execute(
        sa.text(
            f"UPDATE {TABLE} SET {COLUMN} = COALESCE(created_time, CURRENT_TIMESTAMP) "
            f"WHERE {COLUMN} IS NULL"
        )
    )
    op.alter_column(TABLE, COLUMN, existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    op.drop_column(TABLE, COLUMN)
