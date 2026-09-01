"""Remove the retired customer profile storage and vector evidence paths.

Revision ID: 117_remove_legacy_customer_profile_fields
Revises: 116_profile_quality_report
Create Date: 2026-09-01

This is an intentional hard cutover.  Customer profile data is owned only by
crm_customer_profile_projection_versions/current.  The removed columns and
vector source types are not compatibility storage and are not restored by the
application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "117_remove_legacy_customer_profile_fields"
down_revision: str | None = "116_profile_quality_report"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_CUSTOMER_COLUMNS = (
    "company_background",
    "company_website",
    "main_business",
    "similar_customers",
    "project_background",
    "profile_status",
    "profile_generated_time",
    "profile_error_message",
    "customer_brief_json",
    "customer_brief_markdown",
    "customer_brief_citations",
    "customer_brief_status",
    "customer_brief_generated_time",
    "customer_brief_error_message",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("crm_customers")}
    for column_name in _LEGACY_CUSTOMER_COLUMNS:
        if column_name in columns:
            op.drop_column("crm_customers", column_name)

    # These documents are derived solely from the removed Customer columns.
    # Keeping them would expose stale data through semantic retrieval.
    op.execute(
        sa.text(
            "DELETE FROM crm_customer_vector_documents "
            "WHERE source_type IN ('customer_profile', 'customer_brief')"
        )
    )


def downgrade() -> None:
    # The application intentionally has no downgrade compatibility path.  The
    # schema can only be restored manually if a deployment rollback requires it;
    # historical column values cannot be reconstructed from the projection.
    raise RuntimeError(
        "117_remove_legacy_customer_profile_fields is an irreversible data cleanup; "
        "restore from backup instead of downgrading"
    )
