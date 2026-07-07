"""add approval_id to crm_license_applications

Revision ID: 017_license_approval_field
Revises: 016_payment_approval_fields
Create Date: 2026-07-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '017_license_approval_field'
down_revision = '016_payment_approval_fields'
branch_labels = None
depends_on = None


def upgrade():
    """添加 approval_id 字段到 License 申请表"""
    # Add approval_id column to crm_license_applications
    op.add_column(
        'crm_license_applications',
        sa.Column('approval_id', sa.BigInteger(), nullable=True, comment='审批实例ID')
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_license_applications_approval_id',
        'crm_license_applications',
        'crm_contract_approvals',
        ['approval_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add index for approval_id
    op.create_index(
        'idx_license_approval_id',
        'crm_license_applications',
        ['approval_id']
    )


def downgrade():
    """回滚 approval_id 字段"""
    # Remove index
    op.drop_index('idx_license_approval_id', 'crm_license_applications')

    # Remove foreign key constraint
    op.drop_constraint('fk_license_applications_approval_id', 'crm_license_applications', type_='foreignkey')

    # Remove column
    op.drop_column('crm_license_applications', 'approval_id')