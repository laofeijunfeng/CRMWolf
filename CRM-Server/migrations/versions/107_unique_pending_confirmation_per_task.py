"""Guarantee one pending confirmation Case per follow-up task.

Revision ID: 107_unique_pending_confirmation
Revises: 106_postpone_batch_matcher
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "107_unique_pending_confirmation"
down_revision: str | None = "106_postpone_batch_matcher"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "crm_follow_up_task_confirmation_cases"
UNIQUE_NAME = "uq_follow_up_task_confirmation_pending_task"
SUPERSEDED_REASON = "DUPLICATE_ACTIVE_CASE_SUPERSEDED"


def upgrade() -> None:
    # Keep the newest pending Case for each task. Older rows remain as audited
    # history and are terminalized instead of being deleted.
    op.execute(
        sa.text(
            f"""
            UPDATE {TABLE_NAME} AS duplicate_case
            INNER JOIN {TABLE_NAME} AS retained_case
                ON retained_case.team_id = duplicate_case.team_id
               AND retained_case.task_id = duplicate_case.task_id
               AND retained_case.status = 'PENDING'
               AND (
                    retained_case.created_time > duplicate_case.created_time
                    OR (
                        retained_case.created_time = duplicate_case.created_time
                        AND retained_case.id > duplicate_case.id
                    )
               )
            SET duplicate_case.status = 'CANCELLED',
                duplicate_case.cancelled_at = CURRENT_TIMESTAMP,
                duplicate_case.cancelled_reason = :cancelled_reason,
                duplicate_case.updated_time = CURRENT_TIMESTAMP
            WHERE duplicate_case.status = 'PENDING'
            """
        ).bindparams(cancelled_reason=SUPERSEDED_REASON)
    )
    # A stored generated column cannot depend on task_id because task_id is
    # protected by an ON DELETE CASCADE foreign key in MySQL. A functional
    # unique index enforces the same invariant without changing task identity
    # or blocking multiple terminal Case rows.
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX {UNIQUE_NAME}
            ON {TABLE_NAME} (
                team_id,
                ((CASE WHEN status = 'PENDING' THEN task_id ELSE NULL END))
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_index(UNIQUE_NAME, table_name=TABLE_NAME)
