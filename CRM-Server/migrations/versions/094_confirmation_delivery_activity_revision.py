"""Persist confirmation case and delivery source activity revision contracts.

Revision ID: 094_confirmation_delivery_activity_revision
Revises: 093_agent_confirmed_application_task_claim
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "094_confirmation_delivery_activity_revision"
down_revision: str | None = "093_agent_confirmed_application_task_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_follow_up_task_confirmation_prompt_deliveries"
INDEX = "idx_follow_up_confirmation_prompt_activity_revision"
CASE_TABLE = "crm_follow_up_task_confirmation_cases"
CASE_INDEX = "idx_follow_up_confirmation_source_revision"


def upgrade() -> None:
    op.add_column(
        CASE_TABLE,
        sa.Column("source_activity_revision", sa.Integer(), nullable=True, comment="来源客户活动修订号"),
    )
    op.create_index(
        CASE_INDEX,
        CASE_TABLE,
        ["team_id", "source_activity_id", "source_activity_revision"],
    )
    op.add_column(
        TABLE,
        sa.Column("source_activity_id", sa.BigInteger(), nullable=True, comment="来源客户活动ID"),
    )
    op.add_column(
        TABLE,
        sa.Column("expected_activity_revision", sa.Integer(), nullable=True, comment="投递绑定的客户活动修订号"),
    )
    op.create_index(op.f(f"ix_{TABLE}_source_activity_id"), TABLE, ["source_activity_id"])
    op.create_index(
        INDEX,
        TABLE,
        ["team_id", "source_activity_id", "expected_activity_revision"],
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_index(op.f(f"ix_{TABLE}_source_activity_id"), table_name=TABLE)
    op.drop_column(TABLE, "expected_activity_revision")
    op.drop_column(TABLE, "source_activity_id")
    op.drop_index(CASE_INDEX, table_name=CASE_TABLE)
    op.drop_column(CASE_TABLE, "source_activity_revision")
