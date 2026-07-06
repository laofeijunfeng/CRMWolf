"""add approval_id and proof_file_path to payment_records

Revision ID: 016_payment_approval_fields
Revises: 015_add_deployment_and_license_tables
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '016_payment_approval_fields'
down_revision = '015_add_deployment_and_license_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Add approval_id column to crm_payment_records
    op.add_column(
        'crm_payment_records',
        sa.Column('approval_id', sa.BigInteger(), nullable=True, comment='审批实例ID')
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_payment_records_approval_id',
        'crm_payment_records',
        'crm_contract_approvals',
        ['approval_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add proof_file_path column (for file upload feature)
    op.add_column(
        'crm_payment_records',
        sa.Column('proof_file_path', sa.String(500), nullable=True, comment='凭证文件路径')
    )


def downgrade():
    # Remove foreign key constraint
    op.drop_constraint('fk_payment_records_approval_id', 'crm_payment_records', type_='foreignkey')

    # Remove columns
    op.drop_column('crm_payment_records', 'approval_id')
    op.drop_column('crm_payment_records', 'proof_file_path')