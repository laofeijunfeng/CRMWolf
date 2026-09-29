"""Add replayable conversation event identity to assistant actions.

Revision ID: 146_assistant_conversation_events
Revises: 145_assistant_turns
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "146_assistant_conversation_events"
down_revision: str | None = "145_assistant_turns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crm_assistant_actions", sa.Column("event_type", sa.String(length=32), nullable=True))
    op.add_column("crm_assistant_actions", sa.Column("event_key", sa.String(length=128), nullable=True))
    op.add_column("crm_assistant_actions", sa.Column("correlation_id", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_assistant_action_event",
        "crm_assistant_actions",
        ["team_id", "task_id", "event_key"],
        unique=True,
        postgresql_where=sa.text("event_key IS NOT NULL"),
        mysql_length={"event_key": 128},
    )


def downgrade() -> None:
    op.drop_index("uq_assistant_action_event", table_name="crm_assistant_actions")
    op.drop_column("crm_assistant_actions", "correlation_id")
    op.drop_column("crm_assistant_actions", "event_key")
    op.drop_column("crm_assistant_actions", "event_type")
