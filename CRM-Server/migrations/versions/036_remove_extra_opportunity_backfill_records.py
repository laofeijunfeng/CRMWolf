"""remove extra opportunity backfill records

Revision ID: 036_remove_extra_opportunity_backfill_records
Revises: 035_backfill_opportunity_approval_snapshots
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "036_remove_extra_opportunity_backfill_records"
down_revision: Union[str, None] = "035_backfill_opportunity_approval_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKFILL_COMMENT = "历史商机审批快照：迁移补齐审批流程记录"


def remove_extra_opportunity_backfill_records(bind) -> None:
    bind.execute(text(
        """
        DELETE FROM crm_contract_approval_records
        WHERE id IN (
            SELECT record_id
            FROM (
                SELECT r.id AS record_id
                FROM crm_contract_approval_records r
                JOIN crm_contract_approvals a ON a.id = r.approval_id
                WHERE a.business_type = 'OPPORTUNITY'
                  AND r.comment = :comment
                  AND EXISTS (
                      SELECT 1 FROM crm_contract_approval_records r2
                      WHERE r2.approval_id = r.approval_id
                        AND r2.id <> r.id
                        AND (r2.comment IS NULL OR r2.comment <> :comment)
                  )
            ) extra_records
        )
        """
    ), {"comment": BACKFILL_COMMENT})


def upgrade() -> None:
    remove_extra_opportunity_backfill_records(op.get_bind())


def downgrade() -> None:
    pass
