"""contract soft delete and approval no cascade

Revision ID: 010
Revises: 009_system_configs
Create Date: 2026-07-01 11:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009_system_configs'
branch_labels = None
depends_on = None


def upgrade():
    # 1. 给合同表添加 deleted_at 字段（软删除）
    op.add_column(
        'crm_contracts',
        sa.Column('deleted_at', sa.DateTime(), nullable=True, comment='删除时间（软删除标记）')
    )
    op.create_index('idx_contract_deleted', 'crm_contracts', ['deleted_at'])

    # 2. 修改审批实例表的外键配置：移除级联删除
    # SQLite 不支持直接修改外键，需要重建表
    # MySQL 支持 ALTER TABLE DROP FOREIGN KEY + ADD FOREIGN KEY

    # 先获取当前数据库类型
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'mysql':
        # MySQL: 直接修改外键约束
        # 先删除旧的外键约束
        op.drop_constraint('crm_contract_approvals_ibfk_1', 'crm_contract_approvals', type_='foreignkey')
        # 重新添加外键约束，使用 SET NULL 而不是 CASCADE
        op.create_foreign_key(
            'crm_contract_approvals_ibfk_1',
            'crm_contract_approvals',
            'crm_contracts',
            ['contract_id'],
            ['id'],
            ondelete='SET NULL'
        )
    else:
        # SQLite/PostgreSQL: 需要重建表
        # 这里暂时跳过，后续根据实际数据库类型补充
        pass


def downgrade():
    # 1. 移除合同表的 deleted_at 字段
    op.drop_index('idx_contract_deleted', 'crm_contracts')
    op.drop_column('crm_contracts', 'deleted_at')

    # 2. 恢复审批实例表的外键配置：级联删除
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'mysql':
        op.drop_constraint('crm_contract_approvals_ibfk_1', 'crm_contract_approvals', type_='foreignkey')
        op.create_foreign_key(
            'crm_contract_approvals_ibfk_1',
            'crm_contract_approvals',
            'crm_contracts',
            ['contract_id'],
            ['id'],
            ondelete='CASCADE'
        )