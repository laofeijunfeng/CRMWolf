"""make approval contract_id nullable for generic approvals

Revision ID: 021_nullable_approval_contract_id
Revises: 020_payment_plan_number
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '021_nullable_approval_contract_id'
down_revision: Union[str, None] = '020_payment_plan_number'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Generic approvals use business_type/business_id; contract_id is legacy-only."""
    op.alter_column(
        'crm_contract_approvals',
        'contract_id',
        existing_type=sa.BigInteger(),
        nullable=True,
        existing_comment='关联合同ID（合同删除后置空，审批记录保留）',
    )


def downgrade() -> None:
    op.alter_column(
        'crm_contract_approvals',
        'contract_id',
        existing_type=sa.BigInteger(),
        nullable=False,
        existing_comment='关联合同ID（合同删除后置空，审批记录保留）',
    )
