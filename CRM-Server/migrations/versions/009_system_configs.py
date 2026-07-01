"""create crm_system_configs table

Revision ID: 009_system_configs
Revises: 008_ai_conversation_history
Create Date: 2026-07-01

创建系统配置表 crm_system_configs：
- id: 主键
- team_id: 团队ID（团队隔离）
- config_key: 配置键
- config_value: 配置值
- config_type: 配置类型（notification | security | integration）
- description: 配置描述
- created_time: 创建时间
- updated_time: 更新时间

用于存储飞书通知配置等系统配置项。

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_system_configs'
down_revision = '008_ai_conversation_history'
branch_labels = None
depends_on = None


def upgrade():
    # 创建系统配置表
    op.create_table(
        'crm_system_configs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('team_id', sa.BigInteger(), nullable=False, comment='团队ID'),
        sa.Column('config_key', sa.String(100), nullable=False, comment='配置键'),
        sa.Column('config_value', sa.Text(), nullable=False, comment='配置值'),
        sa.Column('config_type', sa.String(50), nullable=False, comment='配置类型：notification | security | integration'),
        sa.Column('description', sa.String(200), nullable=True, comment='配置描述'),
        sa.Column('created_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_time', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'config_key', name='uk_team_key'),
        comment='系统配置表'
    )

    # 创建索引
    op.create_index(
        'idx_system_configs_team',
        'crm_system_configs',
        ['team_id']
    )
    op.create_index(
        'idx_system_configs_type',
        'crm_system_configs',
        ['config_type']
    )


def downgrade():
    # 删除索引
    op.drop_index('idx_system_configs_type', 'crm_system_configs')
    op.drop_index('idx_system_configs_team', 'crm_system_configs')

    # 删除表
    op.drop_table('crm_system_configs')