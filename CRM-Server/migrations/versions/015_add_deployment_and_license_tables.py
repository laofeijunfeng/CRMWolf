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
    # 1. 创建 crm_deployment_infos 表（与模型对齐）
    op.create_table(
        'crm_deployment_infos',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('team_id', sa.BigInteger(), nullable=False, comment='团队ID'),
        sa.Column('customer_id', sa.BigInteger(), nullable=False, comment='关联客户ID'),
        sa.Column('deployment_name', sa.String(100), nullable=False, comment='部署名称（如：生产环境、测试环境）'),
        sa.Column('server_address', sa.String(500), nullable=False, comment='服务器地址（http:// 或 https:// 开头）'),
        sa.Column('authorized_users', sa.Integer(), nullable=False, comment='授权人数'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='0', comment='是否默认部署'),
        sa.Column('created_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('last_modified_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='最后修改时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['customer_id'], ['crm_customers.id'], ondelete='CASCADE'),
        mysql_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    op.create_index('idx_deployment_customer_id', 'crm_deployment_infos', ['customer_id'])
    op.create_index('idx_deployment_team_id', 'crm_deployment_infos', ['team_id'])

    # 2. 创建 crm_license_applications 表（与模型对齐 + 补充字段）
    op.create_table(
        'crm_license_applications',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('team_id', sa.BigInteger(), nullable=False, comment='团队ID'),
        sa.Column('application_number', sa.String(50), nullable=False, comment='申请单号（自动生成）'),
        sa.Column('customer_id', sa.BigInteger(), nullable=False, comment='关联客户ID'),
        sa.Column('deployment_info_id', sa.BigInteger(), nullable=True, comment='关联部署信息ID'),
        sa.Column('contract_id', sa.BigInteger(), nullable=True, comment='关联合同ID'),
        sa.Column('expiry_date', sa.Date(), nullable=False, comment='到期时间'),
        sa.Column('license_type', sa.String(20), nullable=False, comment='License 类型'),
        # 补充需求字段（Task 14）
        sa.Column('enterprise_id', sa.String(50), nullable=True, comment='企业编号（审批人回填）'),
        sa.Column('supported_modules', sa.String(500), nullable=True, comment='支持模块（审批人回填）'),
        sa.Column('server_license_code', sa.Text(), nullable=True, comment='服务端 License（审批人回填）'),
        sa.Column('client_license_code', sa.Text(), nullable=True, comment='客户端 License（审批人回填）'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注（申请时填写）'),
        # 原有授权码字段（兼容保留）
        sa.Column('license_code', sa.Text(), nullable=True, comment='授权码（审批人回填，旧字段）'),
        sa.Column('status', sa.String(20), nullable=False, server_default='DRAFT', comment='申请状态'),
        sa.Column('applicant_id', sa.String(100), nullable=False, comment='申请人飞书用户ID'),
        sa.Column('approver_id', sa.String(100), nullable=True, comment='审批人飞书用户ID'),
        sa.Column('approved_time', sa.DateTime(), nullable=True, comment='审批时间'),
        sa.Column('created_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('last_modified_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='最后修改时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_number', name='uq_application_number'),
        sa.ForeignKeyConstraint(['customer_id'], ['crm_customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deployment_info_id'], ['crm_deployment_infos.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contract_id'], ['crm_contracts.id'], ondelete='SET NULL'),
        mysql_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    op.create_index('idx_license_customer_id', 'crm_license_applications', ['customer_id'])
    op.create_index('idx_license_contract_id', 'crm_license_applications', ['contract_id'])
    op.create_index('idx_license_status', 'crm_license_applications', ['status'])
    op.create_index('idx_license_team_id', 'crm_license_applications', ['team_id'])

    # 3. 为 crm_customers 表新增 license_expiry_date 和 license_type 字段（Task 15）
    op.add_column(
        'crm_customers',
        sa.Column('license_expiry_date', sa.Date(), nullable=True, comment='客户 License 最晚到期时间（自动更新）')
    )
    op.add_column(
        'crm_customers',
        sa.Column('license_type', sa.String(20), nullable=True, comment='客户 License 类型（自动更新）：TRIAL/OFFICIAL')
    )
    op.create_index('idx_customer_license_expiry', 'crm_customers', ['license_expiry_date'])


def downgrade() -> None:
    # 回滚顺序与创建相反
    op.drop_index('idx_customer_license_expiry', 'crm_customers')
    op.drop_column('crm_customers', 'license_type')
    op.drop_column('crm_customers', 'license_expiry_date')

    op.drop_index('idx_license_team_id', 'crm_license_applications')
    op.drop_index('idx_license_status', 'crm_license_applications')
    op.drop_index('idx_license_contract_id', 'crm_license_applications')
    op.drop_index('idx_license_customer_id', 'crm_license_applications')
    op.drop_table('crm_license_applications')

    op.drop_index('idx_deployment_team_id', 'crm_deployment_infos')
    op.drop_index('idx_deployment_customer_id', 'crm_deployment_infos')
    op.drop_table('crm_deployment_infos')