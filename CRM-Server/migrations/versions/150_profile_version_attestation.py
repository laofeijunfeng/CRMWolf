"""Certify new legacy profile versions without trusting historical profile content.

Revision ID: 150_profile_version_attestation
Revises: 149_assistant_command_operator
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "150_profile_version_attestation"
down_revision: str | None = "149_assistant_command_operator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL for all existing versions: customer progress alone does not prove
    # that a historical narrative or evidence registry was eligible.
    op.add_column(
        "crm_customer_profile_projection_versions",
        sa.Column("source_attestation_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "crm_customer_profile_projection_versions",
        sa.Column("source_discriminator", sa.String(length=32), nullable=True),
    )
    op.drop_constraint("uq_customer_profile_projection_content_watermark",
                       "crm_customer_profile_projection_versions", type_="unique")
    op.create_unique_constraint("uq_customer_profile_projection_content_watermark",
                                "crm_customer_profile_projection_versions",
                                ["team_id", "customer_id", "content_hash", "source_discriminator",
                                 "source_watermark_hash"])


def downgrade() -> None:
    # Unsafe to roll back the read-policy with this DDL alone. An operator must
    # stop publication and preserve certified-read gating before downgrade.
    op.drop_constraint("uq_customer_profile_projection_content_watermark",
                       "crm_customer_profile_projection_versions", type_="unique")
    op.create_unique_constraint("uq_customer_profile_projection_content_watermark",
                                "crm_customer_profile_projection_versions",
                                ["team_id", "customer_id", "content_hash", "source_watermark_hash"])
    op.drop_column("crm_customer_profile_projection_versions", "source_discriminator")
    op.drop_column("crm_customer_profile_projection_versions", "source_attestation_json")
