"""Enforce one confirmed application intent per Agent task.

Revision ID: 093_agent_confirmed_application_task_claim
Revises: 092_agent_confirmed_application_steps
Create Date: 2026-08-14
"""
from collections.abc import Sequence

from alembic import op

revision: str = "093_agent_confirmed_application_task_claim"
down_revision: str | None = "092_agent_confirmed_application_steps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_agent_confirmed_application_steps"
CONSTRAINT = "uq_agent_confirmed_application_task"


def upgrade() -> None:
    op.create_unique_constraint(
        CONSTRAINT,
        TABLE,
        ["team_id", "user_id", "task_id"],
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, type_="unique")
