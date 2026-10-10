"""Remove the nine retired customer fact types and mark ineligible vector documents.

Revision ID: 152_remove_customer_profile_prepare
Revises: 151_assistant_proposal_policy
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "152_remove_customer_profile_prepare"
down_revision: str | None = "151_assistant_proposal_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETIRED_FACT_TYPES = (
    "need",
    "budget",
    "risk",
    "stage",
    "stakeholder_attitude",
    "competitor",
    "next_step",
    "preference",
    "summary",
)

# Vector sources that remain rebuildable from raw CRM business objects.
RETAINED_VECTOR_SOURCE_TYPES = (
    "business_flow",
    "follow_up",
    "follow_up_task",
    "sales_commitment",
)


def upgrade() -> None:
    connection = op.get_bind()

    retired = sa.text("SELECT id FROM crm_customer_facts WHERE fact_type IN :types").bindparams(
        sa.bindparam("types", value=list(RETIRED_FACT_TYPES), expanding=True),
    )
    retired_ids = [row.id for row in connection.execute(retired)]

    if retired_ids:
        fact_ids = sa.text("DELETE FROM crm_customer_facts WHERE id IN :ids").bindparams(
            sa.bindparam("ids", value=retired_ids, expanding=True),
        )
        connection.execute(fact_ids)

    sources = sa.text(
        "DELETE FROM crm_customer_fact_sources WHERE fact_id IN :ids"
    ).bindparams(sa.bindparam("ids", value=retired_ids or [0], expanding=True))
    connection.execute(sources)

    revisions = sa.text(
        "DELETE FROM crm_customer_fact_revisions WHERE fact_id IN :ids"
    ).bindparams(sa.bindparam("ids", value=retired_ids or [0], expanding=True))
    connection.execute(revisions)

    mark_delete = sa.text(
        "UPDATE crm_customer_vector_documents "
        "SET sync_status = 'DELETE_PENDING', sync_error = NULL "
        "WHERE source_type NOT IN :types AND sync_status NOT IN ('DELETE_PENDING', 'DELETED')"
    ).bindparams(sa.bindparam("types", value=list(RETAINED_VECTOR_SOURCE_TYPES), expanding=True))
    connection.execute(mark_delete)

    # Clean forbidden customer memory sections; keep qualified retrieval entries.
    for section in ("facts", "summaries", "preferences"):
        connection.execute(
            sa.text(
                "DELETE FROM crm_agent_memory_entries "
                "WHERE namespace LIKE :prefix"
            ),
            {"prefix": f"%/customer/%/{section}"},
        )


def downgrade() -> None:
    # Retired fact rows are deleted physically; recovery requires the pre-release backup.
    raise RuntimeError("Retired customer facts cannot be restored by downgrade")
