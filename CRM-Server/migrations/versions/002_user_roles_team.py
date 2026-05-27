"""Phase 0: Add team_id to user_roles

Revision ID: 002_user_roles_team
Revises: 001_initial
Create Date: 2025-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002_user_roles_team'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 user_roles 表添加 team_id 字段"""
    # 1. 添加 team_id 列（先允许 NULL）
    op.add_column('user_roles', sa.Column('team_id', sa.BigInteger(), nullable=True))

    # 2. 为现有数据设置 team_id（取用户所属的第一个团队）
    # 假设用户通过 current_team_id 或 teams 关联
    op.execute("""
        UPDATE user_roles ur
        SET team_id = (
            SELECT MIN(ct.team_id)
            FROM crm_customer_teams ct
            WHERE ct.user_id = ur.user_id
        )
        WHERE ur.team_id IS NULL
    """)

    # 3. 处理没有团队的用户的 user_roles（分配到默认团队，如果存在）
    op.execute("""
        UPDATE user_roles ur
        SET team_id = (
            SELECT id FROM crm_teams WHERE is_default = 1 LIMIT 1
        )
        WHERE ur.team_id IS NULL
    """)

    # 4. 删除旧的唯一约束（如果存在）
    try:
        op.drop_constraint('uq_user_role', 'user_roles', type_='unique')
    except:
        pass

    # 5. 设置 NOT NULL
    op.alter_column('user_roles', 'team_id', nullable=False)

    # 6. 添加索引
    op.create_index('idx_user_roles_team_id', 'user_roles', ['team_id'])

    # 7. 添加新的唯一约束
    op.create_unique_constraint('uq_user_role_team', 'user_roles', ['user_id', 'team_id', 'role_id'])


def downgrade() -> None:
    """回滚 user_roles 表的 team_id"""
    # 1. 删除唯一约束
    op.drop_constraint('uq_user_role_team', 'user_roles', type_='unique')

    # 2. 删除索引
    op.drop_index('idx_user_roles_team_id', 'user_roles')

    # 3. 删除列
    op.drop_column('user_roles', 'team_id')