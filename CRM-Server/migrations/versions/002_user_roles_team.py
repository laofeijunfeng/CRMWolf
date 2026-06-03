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
    conn = op.get_bind()

    # 1. 添加 team_id 列（先允许 NULL）
    op.add_column('user_roles', sa.Column('team_id', sa.BigInteger(), nullable=True))

    # 2. 为现有数据设置 team_id（取用户的当前团队）
    # 使用正确的表名: user_teams
    conn.execute(sa.text("""
        UPDATE user_roles ur
        SET team_id = (
            SELECT ut.team_id
            FROM user_teams ut
            WHERE ut.user_id = ur.user_id AND ut.current_team = 1
            LIMIT 1
        )
        WHERE ur.team_id IS NULL
    """))

    # 3. 处理没有当前团队的 user_roles（取第一个所属团队）
    conn.execute(sa.text("""
        UPDATE user_roles ur
        SET team_id = (
            SELECT MIN(ut.team_id)
            FROM user_teams ut
            WHERE ut.user_id = ur.user_id
        )
        WHERE ur.team_id IS NULL
    """))

    # 4. 处理完全没有团队的 user_roles（取第一个团队作为默认）
    conn.execute(sa.text("""
        UPDATE user_roles ur
        SET team_id = (
            SELECT MIN(id) FROM teams
        )
        WHERE ur.team_id IS NULL
    """))

    # 5. 删除旧的唯一约束（如果存在）
    try:
        op.drop_constraint('uq_user_role', 'user_roles', type_='unique')
    except:
        pass

    # 6. 设置 NOT NULL
    op.alter_column('user_roles', 'team_id', nullable=False)

    # 7. 添加索引
    op.create_index('idx_user_roles_team_id', 'user_roles', ['team_id'])

    # 8. 添加新的唯一约束
    op.create_unique_constraint('uq_user_role_team', 'user_roles', ['user_id', 'team_id', 'role_id'])


def downgrade() -> None:
    """回滚 user_roles 表的 team_id"""
    # 1. 删除唯一约束
    op.drop_constraint('uq_user_role_team', 'user_roles', type_='unique')

    # 2. 删除索引
    op.drop_index('idx_user_roles_team_id', 'user_roles')

    # 3. 删除列
    op.drop_column('user_roles', 'team_id')