"""Make Agent UI action participation in Root context explicit.

Revision ID: 109_agent_ui_action_root_context_role
Revises: 108_agent_message_history_owner_order_index
Create Date: 2026-08-27
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "109_agent_ui_action_root_context_role"
down_revision: str | None = "108_agent_message_history_owner_order_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "crm_agent_ui_actions"
COLUMN_NAME = "root_context_role"
INDEX_NAME = "idx_agent_ui_action_root_context_role"


def upgrade() -> None:
    """Backfill one authoritative role and then make it mandatory."""
    op.add_column(
        TABLE_NAME,
        sa.Column(
            COLUMN_NAME,
            sa.String(length=24),
            nullable=True,
            comment="Root上下文角色: 可恢复Workflow、待确认事项或仅展示投影",
        ),
    )
    # Existing submit_interaction actions were created by the native Workflow
    # runtime.  Follow-up confirmation projections carry an explicit Case ID in
    # their signed target and are therefore business pending Cases, not Root
    # continuations.  All other historical actions are presentation-only.
    op.execute(
        sa.text(
            f"""
            UPDATE {TABLE_NAME}
            SET {COLUMN_NAME} = CASE
                WHEN action_type = 'submit_interaction'
                 AND JSON_EXTRACT(target_json, '$.follow_up_confirmation_case_public_id') IS NOT NULL
                    THEN 'PENDING_CASE'
                WHEN action_type = 'submit_interaction'
                    THEN 'RESUMABLE_WORKFLOW'
                ELSE 'PROJECTION_ONLY'
            END
            WHERE {COLUMN_NAME} IS NULL
            """
        )
    )
    op.alter_column(TABLE_NAME, COLUMN_NAME, existing_type=sa.String(length=24), nullable=False)
    op.create_index(INDEX_NAME, TABLE_NAME, ["team_id", "user_id", "session_id", COLUMN_NAME, "status"])


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    op.drop_column(TABLE_NAME, COLUMN_NAME)
