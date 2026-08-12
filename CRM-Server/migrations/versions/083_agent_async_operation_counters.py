"""add serialized counters to agent async operations

Revision ID: 083_agent_async_operation_counters
Revises: 082_agent_async_operations
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "083_agent_async_operation_counters"
down_revision: str | None = "082_agent_async_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_agent_async_operations",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0", comment="已开始执行次数"),
    )
    op.add_column(
        "crm_agent_async_operations",
        sa.Column("next_event_sequence", sa.Integer(), nullable=False, server_default="1", comment="下一个事件序号"),
    )
    op.execute(
        """
        UPDATE crm_agent_async_operations operation_row
        SET next_event_sequence = COALESCE((
            SELECT MAX(event_row.sequence) + 1
            FROM crm_agent_async_operation_events event_row
            WHERE event_row.operation_id = operation_row.id
        ), 1)
        """
    )


def downgrade() -> None:
    op.drop_column("crm_agent_async_operations", "next_event_sequence")
    op.drop_column("crm_agent_async_operations", "attempt_count")
