"""Add per-customer legacy source progress without certifying historical projections.

Revision ID: 148_assistant_legacy_source_guard
Revises: 147_assistant_crm_effects
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "148_assistant_legacy_source_guard"
down_revision: str | None = "147_assistant_crm_effects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_customer_legacy_source_progress",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("eligible_revision", sa.BigInteger(), nullable=False),
        sa.Column("deletion_revision", sa.BigInteger(), nullable=False),
        sa.Column("provenance_status", sa.String(length=20), nullable=False),
        sa.UniqueConstraint("team_id", "customer_id", name="uq_customer_legacy_source_progress"),
    )
    op.create_index("idx_customer_legacy_progress_team_customer", "crm_customer_legacy_source_progress", ["team_id", "customer_id"])
    # Idempotent bootstrap: policy and counts are historical diagnostics, not
    # an assertion that previous profile text/citations have passed verification.
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO crm_customer_legacy_source_progress
            (team_id, customer_id, policy_version, eligible_revision, deletion_revision, provenance_status)
        SELECT c.team_id, c.id, 'LEGACY_PROFILE_ELIGIBLE_V1',
            (SELECT COUNT(*) FROM crm_customer_activities a
             WHERE a.team_id = c.team_id AND a.customer_id = c.id AND a.submission_source IN ('FORM', 'AGENT', 'CUTOVER_MIGRATION')) +
            (SELECT COUNT(*) FROM crm_customer_activity_deletion_tombstones t
             WHERE t.team_id = c.team_id AND t.customer_id = c.id AND t.submission_source IN ('FORM', 'AGENT', 'CUTOVER_MIGRATION')),
            (SELECT COUNT(*) FROM crm_customer_activity_deletion_tombstones t
             WHERE t.team_id = c.team_id AND t.customer_id = c.id AND t.submission_source IN ('FORM', 'AGENT', 'CUTOVER_MIGRATION')),
            'UNVERIFIED'
        FROM crm_customers c
        WHERE NOT EXISTS (
            SELECT 1 FROM crm_customer_legacy_source_progress p
            WHERE p.team_id = c.team_id AND p.customer_id = c.id
        )
    """))


def downgrade() -> None:
    op.drop_index("idx_customer_legacy_progress_team_customer", table_name="crm_customer_legacy_source_progress")
    op.drop_table("crm_customer_legacy_source_progress")
