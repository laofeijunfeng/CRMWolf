# CRM-Server/migrations/versions/015_add_deployment_and_license_tables.py
"""add deployment_infos and license_applications tables

Revision ID: 015_add_deployment_and_license_tables
Revises: 014_invoice_file_path
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = '015_add_deployment_and_license_tables'
down_revision: str = '014_invoice_file_path'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建 crm_deployment_infos 表
    op.create_table(
        'crm_deployment_infos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
        sa.Column('customer_id', sa.Integer(), nullable=False, comment='客户ID'),
        sa.Column('deployment_name', sa.String(100), nullable=False, comment='部署名称'),
        sa.Column('server_address', sa.String(255), nullable=False, comment='服务器地址'),
        sa.Column('description', sa.Text(), nullable=True, comment='描述'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0', comment='软删除标记'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['customer_id'], ['crm_customers.id'], ondelete='CASCADE'),
        mysql_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    op.create_index('idx_deployment_customer', 'crm_deployment_infos', ['customer_id'])
    op.create_index('idx_deployment_name', 'crm_deployment_infos', ['deployment_name'])

    # 2. 创建 crm_license_applications 表
    op.create_table(
        'crm_license_applications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
        sa.Column('application_no', sa.String(50), nullable=False, comment='申请编号'),
        sa.Column('customer_id', sa.Integer(), nullable=False, comment='客户ID'),
        sa.Column('contract_id', sa.Integer(), nullable=True, comment='合同ID（试用License可为空）'),
        sa.Column('deployment_id', sa.Integer(), nullable=False, comment='部署信息ID'),
        sa.Column('license_type', sa.String(20), nullable=False, comment='License类型（trial/formal）'),
        sa.Column('license_expiry_date', sa.Date(), nullable=False, comment='License到期日期'),
        sa.Column('status', sa.String(20), nullable=False, server_default='DRAFT', comment='申请状态（DRAFT/PENDING/APPROVED/REJECTED/ISSUED）'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
        sa.Column('license_info', sa.Text(), nullable=True, comment='License授权码信息（审批通过后填写）'),
        sa.Column('created_by', sa.Integer(), nullable=False, comment='创建人ID'),
        sa.Column('approved_by', sa.Integer(), nullable=True, comment='审批人ID'),
        sa.Column('approved_at', sa.DateTime(), nullable=True, comment='审批时间'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0', comment='软删除标记'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['customer_id'], ['crm_customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contract_id'], ['crm_contracts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['deployment_id'], ['crm_deployment_infos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['sys_users.id']),
        sa.ForeignKeyConstraint(['approved_by'], ['sys_users.id']),
        mysql_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    op.create_index('idx_license_application_no', 'crm_license_applications', ['application_no'], unique=True)
    op.create_index('idx_license_customer', 'crm_license_applications', ['customer_id'])
    op.create_index('idx_license_contract', 'crm_license_applications', ['contract_id'])
    op.create_index('idx_license_status', 'crm_license_applications', ['status'])

    # 3. 为 crm_customers 表新增 license_expiry_date 字段
    op.add_column(
        'crm_customers',
        sa.Column('license_expiry_date', sa.Date(), nullable=True, comment='License到期日期')
    )
    op.create_index('idx_customer_license_expiry', 'crm_customers', ['license_expiry_date'])


def downgrade() -> None:
    # 回滚顺序与创建相反
    op.drop_index('idx_customer_license_expiry', 'crm_customers')
    op.drop_column('crm_customers', 'license_expiry_date')

    op.drop_index('idx_license_status', 'crm_license_applications')
    op.drop_index('idx_license_contract', 'crm_license_applications')
    op.drop_index('idx_license_customer', 'crm_license_applications')
    op.drop_index('idx_license_application_no', 'crm_license_applications')
    op.drop_table('crm_license_applications')

    op.drop_index('idx_deployment_name', 'crm_deployment_infos')
    op.drop_index('idx_deployment_customer', 'crm_deployment_infos')
    op.drop_table('crm_deployment_infos')