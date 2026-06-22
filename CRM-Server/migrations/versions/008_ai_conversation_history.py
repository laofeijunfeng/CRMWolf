"""add ai_conversation_history table

Revision ID: 008_ai_conversation_history
Revises: 007_undo_fields
Create Date: 2026-06-17

创建 AI 对话历史表 crm_ai_conversation_history：
- id: 主键
- team_id: 团队ID（团队隔离）
- user_id: 用户ID
- title: 对话标题
- summary: 对话摘要
- action_type: 操作类型
- entity_type: 实体类型
- entity_id: 实体ID
- messages: 对话消息列表（JSON）
- status: 状态
- created_at: 创建时间
- updated_at: 更新时间

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008_ai_conversation_history'
down_revision = '007_undo_fields'
branch_labels = None
depends_on = None


def upgrade():
    # 创建 AI 对话历史表
    op.create_table(
        'crm_ai_conversation_history',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('team_id', sa.BigInteger(), nullable=False, comment='团队ID'),
        sa.Column('user_id', sa.Integer(), nullable=False, comment='用户ID'),
        sa.Column('title', sa.String(200), nullable=False, comment='对话标题'),
        sa.Column('summary', sa.Text(), nullable=True, comment='对话摘要'),
        sa.Column('action_type', sa.String(50), nullable=True, comment='操作类型'),
        sa.Column('entity_type', sa.String(20), nullable=True, comment='实体类型'),
        sa.Column('entity_id', sa.BigInteger(), nullable=True, comment='实体ID'),
        sa.Column('messages', sa.JSON(), nullable=False, comment='对话消息列表'),
        sa.Column('status', sa.String(20), default='active', comment='状态'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI 对话历史表'
    )

    # 创建索引
    op.create_index(
        'idx_ai_conversation_team_user',
        'crm_ai_conversation_history',
        ['team_id', 'user_id']
    )
    op.create_index(
        'idx_ai_conversation_created_at',
        'crm_ai_conversation_history',
        ['created_at']
    )


def downgrade():
    # 删除索引
    op.drop_index('idx_ai_conversation_created_at', 'crm_ai_conversation_history')
    op.drop_index('idx_ai_conversation_team_user', 'crm_ai_conversation_history')

    # 删除表
    op.drop_table('crm_ai_conversation_history')