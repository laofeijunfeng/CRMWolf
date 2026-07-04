# CRM-Server/migrations/versions/014_invoice_file_path.py
"""add invoice_file_path, invoice_number, and issued_time columns

Revision ID: 014_invoice_file_path
Revises: 013_invoice_approval_data_migration
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014_invoice_file_path'
down_revision: str = '013_invoice_approval_data_migration'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 发票文件路径（相对路径）
    op.add_column(
        'crm_invoice_applications',
        sa.Column('invoice_file_path', sa.String(500), nullable=True, comment='发票文件路径（相对路径）')
    )
    # 发票号码（可选字段——财务可从发票文件中查看号码，无需手动填写）
    op.add_column(
        'crm_invoice_applications',
        sa.Column('invoice_number', sa.String(100), nullable=True, comment='发票号码（可选，便于后续查询）')
    )
    # 开票时间（上传发票文件时间）
    op.add_column(
        'crm_invoice_applications',
        sa.Column('issued_time', sa.DateTime(), nullable=True, comment='开票时间（上传发票文件时间）')
    )


def downgrade() -> None:
    op.drop_column('crm_invoice_applications', 'issued_time')
    op.drop_column('crm_invoice_applications', 'invoice_number')
    op.drop_column('crm_invoice_applications', 'invoice_file_path')