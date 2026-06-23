"""add undo fields to operation_log

Revision ID: 007_undo_fields
Revises: 006_industries
Create Date: 2026-06-10

添加撤销机制相关字段到 crm_operation_logs 表：
- undoable: 是否可撤销
- undo_ttl: 撤销窗口（秒）
- undo_deadline: 撤销截止时间
- undone: 是否已撤销
- undo_by: 撤销操作人ID
- undo_at: 撤销时间
- workflow_session_id: Workflow Session ID
- step_id: Workflow 步骤ID
- parent_operation_id: 父操作ID
- before_snapshot: 操作前快照
- after_snapshot: 操作后快照

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_undo_fields'
down_revision = '006_industries'
branch_labels = None
depends_on = None


def upgrade():
    # 添加撤销相关字段
    op.add_column(
        'crm_operation_logs',
        sa.Column('undoable', sa.Boolean(), default=False, comment='是否可撤销')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('undo_ttl', sa.Integer(), default=10, comment='撤销窗口（秒）')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('undo_deadline', sa.DateTime(), nullable=True, comment='撤销截止时间')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('undone', sa.Boolean(), default=False, comment='是否已撤销')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('undo_by', sa.String(100), nullable=True, comment='撤销操作人ID')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('undo_at', sa.DateTime(), nullable=True, comment='撤销时间')
    )

    # 添加 Workflow 关联字段
    op.add_column(
        'crm_operation_logs',
        sa.Column('workflow_session_id', sa.String(64), nullable=True, comment='Workflow Session ID')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('step_id', sa.String(32), nullable=True, comment='Workflow 步骤ID')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('parent_operation_id', sa.BigInteger(), nullable=True, comment='父操作ID（用于级联撤销）')
    )

    # 添加快照字段
    op.add_column(
        'crm_operation_logs',
        sa.Column('before_snapshot', sa.JSON(), nullable=True, comment='操作前状态快照')
    )
    op.add_column(
        'crm_operation_logs',
        sa.Column('after_snapshot', sa.JSON(), nullable=True, comment='操作后状态快照')
    )

    # 创建索引
    op.create_index(
        'idx_workflow_session',
        'crm_operation_logs',
        ['workflow_session_id']
    )
    op.create_index(
        'idx_undoable',
        'crm_operation_logs',
        ['undoable', 'undone', 'undo_deadline']
    )


def downgrade():
    # 删除索引
    op.drop_index('idx_undoable', 'crm_operation_logs')
    op.drop_index('idx_workflow_session', 'crm_operation_logs')

    # 删除快照字段
    op.drop_column('crm_operation_logs', 'after_snapshot')
    op.drop_column('crm_operation_logs', 'before_snapshot')

    # 删除 Workflow 关联字段
    op.drop_column('crm_operation_logs', 'parent_operation_id')
    op.drop_column('crm_operation_logs', 'step_id')
    op.drop_column('crm_operation_logs', 'workflow_session_id')

    # 删除撤销相关字段
    op.drop_column('crm_operation_logs', 'undo_at')
    op.drop_column('crm_operation_logs', 'undo_by')
    op.drop_column('crm_operation_logs', 'undone')
    op.drop_column('crm_operation_logs', 'undo_deadline')
    op.drop_column('crm_operation_logs', 'undo_ttl')
    op.drop_column('crm_operation_logs', 'undoable')