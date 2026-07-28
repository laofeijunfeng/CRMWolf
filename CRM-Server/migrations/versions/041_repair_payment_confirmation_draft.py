"""repair payment confirmation draft values

Revision ID: 041_repair_payment_confirmation_draft
Revises: 040_dedupe_team_customer_and_lead_names
Create Date: 2026-07-28

"""
from typing import Sequence, Union

from alembic import op


revision: str = "041_repair_payment_confirmation_draft"
down_revision: Union[str, None] = "040_dedupe_team_customer_and_lead_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE crm_payment_records
        SET confirmation_status = 'PENDING'
        WHERE confirmation_status = 'DRAFT'
        """
    )


def downgrade() -> None:
    pass
