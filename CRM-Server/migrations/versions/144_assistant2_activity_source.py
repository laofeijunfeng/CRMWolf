"""Allow isolated Assistant 2.0 activities with mandatory submission identity.

Revision ID: 144_assistant2_activity_source
Revises: 143_assistant_tasks
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "144_assistant2_activity_source"
down_revision: str | None = "143_assistant_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "crm_customer_activities"
_TOMBSTONES = "crm_customer_activity_deletion_tombstones"
_SOURCE_CHECK = "ck_customer_activity_submission_source"
_KEY_CHECK = "ck_customer_activity_assistant2_submission"


def upgrade() -> None:
    op.drop_constraint(_SOURCE_CHECK, _TABLE, type_="check")
    op.create_check_constraint(
        _SOURCE_CHECK,
        _TABLE,
        "submission_source IN ('AGENT', 'ASSISTANT_2', 'FORM', 'CUTOVER_MIGRATION')",
    )
    op.create_check_constraint(
        _KEY_CHECK,
        _TABLE,
        "submission_source != 'ASSISTANT_2' OR "
        "(submission_id IS NOT NULL AND LENGTH(TRIM(submission_id)) > 0 "
        "AND submission_fingerprint IS NOT NULL AND LENGTH(TRIM(submission_fingerprint)) = 64)",
    )
    op.add_column(
        _TOMBSTONES,
        sa.Column("submission_source", sa.String(length=30), nullable=False, server_default="FORM"),
    )


def downgrade() -> None:
    # Neither the prior activity CHECK nor the prior tombstone schema can
    # represent Assistant 2.0 provenance. Never discard or relabel user data.
    activity_count = op.get_bind().exec_driver_sql(
        "SELECT COUNT(*) FROM crm_customer_activities WHERE submission_source = 'ASSISTANT_2'"
    ).scalar_one()
    tombstone_count = op.get_bind().exec_driver_sql(
        "SELECT COUNT(*) FROM crm_customer_activity_deletion_tombstones WHERE submission_source = 'ASSISTANT_2'"
    ).scalar_one()
    if activity_count or tombstone_count:
        raise RuntimeError("Cannot downgrade while ASSISTANT_2 activities or tombstones exist")
    op.drop_column(_TOMBSTONES, "submission_source")
    op.drop_constraint(_KEY_CHECK, _TABLE, type_="check")
    op.drop_constraint(_SOURCE_CHECK, _TABLE, type_="check")
    op.create_check_constraint(
        _SOURCE_CHECK,
        _TABLE,
        "submission_source IN ('AGENT', 'FORM', 'CUTOVER_MIGRATION')",
    )
