"""Add an ordered owner lookup index for Agent message history.

Revision ID: 108_agent_message_history_owner_order_index
Revises: 107_unique_pending_confirmation
Create Date: 2026-08-26
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "108_agent_message_history_owner_order_index"
down_revision: str | None = "107_unique_pending_confirmation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "crm_agent_messages"
INDEX_NAME = "idx_agent_message_history_owner_order"


def upgrade() -> None:
    """Avoid index-merge/filesort when paging an owned Agent session history."""
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["team_id", "user_id", "session_id", "created_time", "id"],
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
