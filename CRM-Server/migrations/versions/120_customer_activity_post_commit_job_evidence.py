"""Preserve post-commit job evidence after activity deletion.

Revision ID: 120_customer_activity_post_commit_job_evidence
Revises: 119_customer_activity_ai_jobs
Create Date: 2026-09-02

PostCommitJob rows are durable execution evidence.  They must outlive the
hard-deleted source activity so that deletion, skip, retry and race outcomes
remain auditable and workers cannot recreate side effects from a missing
source row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "120_customer_activity_post_commit_job_evidence"
down_revision: str | None = "119_customer_activity_ai_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_customer_activity_post_commit_jobs"
ACTIVITY_TABLE = "crm_customer_activities"
FK_NAME = "fk_customer_activity_post_commit_jobs_activity"


def _current_activity_fk_name() -> str:
    """Find the pre-120 FK name, including MySQL's generated name."""

    try:
        bind = op.get_bind()
        for constraint in sa.inspect(bind).get_foreign_keys(TABLE):
            if constraint.get("constrained_columns") == ["activity_id"]:
                referred = constraint.get("referred_table")
                if referred == ACTIVITY_TABLE:
                    return str(constraint["name"])
    except Exception:
        # Structural tests and some dialects do not expose inspector metadata.
        # The historical MySQL default is the fallback used by the old table.
        pass
    return f"{TABLE}_ibfk_1"


def upgrade() -> None:
    old_fk_name = _current_activity_fk_name()
    if old_fk_name:
        op.drop_constraint(old_fk_name, TABLE, type_="foreignkey")
    op.create_foreign_key(
        FK_NAME,
        TABLE,
        ACTIVITY_TABLE,
        ["activity_id"],
        ["id"],
        ondelete=None,
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, TABLE, type_="foreignkey")
    op.create_foreign_key(
        f"{TABLE}_ibfk_1",
        TABLE,
        ACTIVITY_TABLE,
        ["activity_id"],
        ["id"],
        ondelete="CASCADE",
    )
