"""add contract owner_id

Revision ID: 022_contract_owner_id
Revises: 021_nullable_approval_contract_id
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '022_contract_owner_id'
down_revision: Union[str, None] = '021_nullable_approval_contract_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _has_column('crm_contracts', 'owner_id'):
        op.add_column(
            'crm_contracts',
            sa.Column('owner_id', sa.String(length=100), nullable=True, comment='合同负责人飞书用户ID'),
        )

    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE crm_contracts c
        LEFT JOIN crm_opportunities o ON o.id = c.opportunity_id
        LEFT JOIN crm_customers cu ON cu.id = c.customer_id
        SET c.owner_id = COALESCE(NULLIF(o.owner_id, ''), NULLIF(cu.owner_id, ''), c.creator_id)
        WHERE c.owner_id IS NULL OR c.owner_id = ''
    """))

    op.alter_column(
        'crm_contracts',
        'owner_id',
        existing_type=sa.String(length=100),
        nullable=False,
        existing_comment='合同负责人飞书用户ID',
    )

    if not _has_index('crm_contracts', 'idx_contract_owner_id'):
        op.create_index('idx_contract_owner_id', 'crm_contracts', ['owner_id'])


def downgrade() -> None:
    if _has_index('crm_contracts', 'idx_contract_owner_id'):
        op.drop_index('idx_contract_owner_id', table_name='crm_contracts')

    if _has_column('crm_contracts', 'owner_id'):
        op.drop_column('crm_contracts', 'owner_id')
