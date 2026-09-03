"""Add the canonical customer-activity workflow data contract.

Revision ID: 118_customer_activity_workflow_contracts
Revises: 117_remove_legacy_customer_profile_fields
Create Date: 2026-09-02

This is the expand/contract boundary for customer activities:
- rename the activity semantic revision to its canonical name;
- persist submission provenance and form idempotency identity;
- constrain activity and post-commit lifecycle values at the database boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "118_customer_activity_workflow_contracts"
down_revision: str | None = "117_remove_legacy_customer_profile_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVITY_TABLE = "crm_customer_activities"
POST_COMMIT_TABLE = "crm_customer_activity_post_commit_jobs"
ORIGIN_TABLE = "crm_customer_activity_agent_origins"


def upgrade() -> None:
    op.alter_column(
        ACTIVITY_TABLE,
        "post_commit_revision",
        new_column_name="activity_revision",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("1"),
        existing_comment="后提交工作流修订号",
        comment="活动语义修订号",
    )
    op.add_column(
        ACTIVITY_TABLE,
        sa.Column(
            "submission_source",
            sa.String(length=30),
            nullable=False,
            server_default="FORM",
            comment="活动提交来源: AGENT/FORM/CUTOVER_MIGRATION",
        ),
    )
    op.add_column(
        ACTIVITY_TABLE,
        sa.Column(
            "submission_id",
            sa.String(length=120),
            nullable=True,
            comment="页面提交幂等ID; Agent 使用 command 幂等",
        ),
    )
    # Existing Agent-origin rows are historical Agent submissions; all other
    # historical activities remain FORM for provenance compatibility.
    op.execute(
        sa.text(
            f"""UPDATE {ACTIVITY_TABLE} AS activity
               SET submission_source = 'AGENT'
             WHERE EXISTS (
                 SELECT 1 FROM {ORIGIN_TABLE} AS origin
                  WHERE origin.team_id = activity.team_id
                    AND origin.activity_id = activity.id
             )"""
        )
    )
    op.create_unique_constraint(
        "uq_customer_activity_submission",
        ACTIVITY_TABLE,
        ["team_id", "submission_id"],
    )
    op.create_index(
        "idx_customer_activity_submission_source",
        ACTIVITY_TABLE,
        ["team_id", "submission_source", "created_time"],
    )
    op.create_check_constraint(
        "ck_customer_activity_submission_source",
        ACTIVITY_TABLE,
        "submission_source IN ('AGENT', 'FORM', 'CUTOVER_MIGRATION')",
    )
    op.create_check_constraint(
        "ck_customer_activity_processing_status",
        ACTIVITY_TABLE,
        "processing_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
    )
    op.create_check_constraint(
        "ck_customer_activity_effectiveness_status",
        ACTIVITY_TABLE,
        "effectiveness_status IS NULL OR effectiveness_status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')",
    )
    op.create_check_constraint(
        "ck_customer_activity_post_commit_job_status",
        POST_COMMIT_TABLE,
        "status IN ('QUEUED', 'RUNNING', 'RETRY_PENDING', 'COMPLETED', 'FAILED', 'SKIPPED', 'EXHAUSTED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_customer_activity_post_commit_job_status", POST_COMMIT_TABLE, type_="check")
    op.drop_constraint("ck_customer_activity_effectiveness_status", ACTIVITY_TABLE, type_="check")
    op.drop_constraint("ck_customer_activity_processing_status", ACTIVITY_TABLE, type_="check")
    op.drop_constraint("ck_customer_activity_submission_source", ACTIVITY_TABLE, type_="check")
    op.drop_index("idx_customer_activity_submission_source", table_name=ACTIVITY_TABLE)
    op.drop_constraint("uq_customer_activity_submission", ACTIVITY_TABLE, type_="unique")
    op.drop_column(ACTIVITY_TABLE, "submission_id")
    op.drop_column(ACTIVITY_TABLE, "submission_source")
    op.alter_column(
        ACTIVITY_TABLE,
        "activity_revision",
        new_column_name="post_commit_revision",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("1"),
        existing_comment="活动语义修订号",
        comment="后提交工作流修订号",
    )
