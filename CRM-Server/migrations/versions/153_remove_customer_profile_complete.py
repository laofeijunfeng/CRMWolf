"""Drop customer profile storage after Qdrant retirement is verified.

Revision ID: 153_remove_customer_profile_complete
Revises: 152_remove_customer_profile_prepare
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "153_remove_customer_profile_complete"
down_revision: str | None = "152_remove_customer_profile_prepare"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()

    pending = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM crm_customer_vector_documents "
            "WHERE sync_status = 'DELETE_PENDING'"
        )
    ).scalar()
    if pending:
        raise RuntimeError(
            f"{pending} vector documents still DELETE_PENDING; retire their Qdrant points first"
        )

    connection.execute(
        sa.text(
            "DELETE FROM crm_customer_vector_documents "
            "WHERE source_type NOT IN ('business_flow', 'follow_up', 'follow_up_task', 'sales_commitment')"
        )
    )

    op.drop_table("crm_customer_profile_current")
    op.drop_table("crm_customer_profile_projection_versions")
    op.drop_table("crm_customer_legacy_source_progress")


def downgrade() -> None:
    raise RuntimeError("Dropped customer profile tables cannot be restored by downgrade")
