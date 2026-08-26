"""Track the authoritative source of customer-activity next actions.

Revision ID: 105_activity_next_action_source
Revises: 104_drop_ci_fact_review
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "105_activity_next_action_source"
down_revision: str | None = "104_drop_ci_fact_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "crm_customer_activities"
COLUMN_NAME = "next_action_source"


def upgrade() -> None:
    op.add_column(
        TABLE_NAME,
        sa.Column(
            COLUMN_NAME,
            sa.String(length=30),
            nullable=True,
            comment="下一步动作来源: UI_DEFAULT/USER/AI_EXTRACTED/AGENT/MIGRATED",
        ),
    )
    op.execute(
        sa.text(
            f"""UPDATE {TABLE_NAME}
                SET {COLUMN_NAME} = 'MIGRATED'
                WHERE next_action IS NOT NULL
                  AND TRIM(next_action) <> ''"""
        )
    )


def downgrade() -> None:
    op.drop_column(TABLE_NAME, COLUMN_NAME)
