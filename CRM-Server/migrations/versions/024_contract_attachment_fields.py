"""add contract attachment fields

Revision ID: 024_contract_attachment_fields
Revises: 024_opportunity_approval_phase
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = '024_contract_attachment_fields'
down_revision = '024_opportunity_approval_phase'
branch_labels = None
depends_on = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name}).scalar() > 0


def upgrade():
    conn = op.get_bind()
    columns = [
        ('contract_file_path', sa.Column('contract_file_path', sa.String(500), nullable=True, comment='合同附件路径（相对路径）')),
        ('contract_file_name', sa.Column('contract_file_name', sa.String(255), nullable=True, comment='合同附件原始文件名')),
        ('contract_file_size', sa.Column('contract_file_size', sa.BigInteger(), nullable=True, comment='合同附件大小（字节）')),
        ('contract_file_mime_type', sa.Column('contract_file_mime_type', sa.String(100), nullable=True, comment='合同附件 MIME 类型')),
    ]
    for column_name, column in columns:
        if not _column_exists(conn, 'crm_contracts', column_name):
            op.add_column('crm_contracts', column)


def downgrade():
    conn = op.get_bind()
    for column_name in [
        'contract_file_mime_type',
        'contract_file_size',
        'contract_file_name',
        'contract_file_path',
    ]:
        if _column_exists(conn, 'crm_contracts', column_name):
            op.drop_column('crm_contracts', column_name)
