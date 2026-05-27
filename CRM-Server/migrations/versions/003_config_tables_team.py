"""Phase 1: Add team_id to core config tables

Revision ID: 003_config_tables_team
Revises: 002_user_roles_team
Create Date: 2025-05-27

迁移表：
- crm_opportunity_stages
- crm_approval_flows
- crm_approval_nodes
- crm_procurement_methods
- crm_procurement_stage_templates

策略：为每个现有团队复制配置数据
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003_config_tables_team'
down_revision: Union[str, None] = '002_user_roles_team'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_TO_MIGRATE = [
    'crm_opportunity_stages',
    'crm_approval_flows',
    'crm_approval_nodes',
    'crm_procurement_methods',
    'crm_procurement_stage_templates',
]


def upgrade() -> None:
    """为核心配置表添加 team_id 并复制数据"""
    conn = op.get_bind()

    # 获取所有团队
    teams = conn.execute(sa.text("SELECT id FROM crm_teams WHERE is_active = 1")).fetchall()
    team_ids = [t[0] for t in teams]

    if not team_ids:
        # 如果没有团队，使用默认团队或创建一个
        default_team = conn.execute(sa.text(
            "SELECT id FROM crm_teams WHERE is_default = 1 LIMIT 1"
        )).fetchone()
        if default_team:
            team_ids = [default_team[0]]
        else:
            # 创建默认团队
            conn.execute(sa.text(
                "INSERT INTO crm_teams (name, code, is_default, is_active) VALUES ('默认团队', 'DEFAULT', 1, 1)"
            ))
            default_team = conn.execute(sa.text("SELECT LAST_INSERT_ID()")).fetchone()
            team_ids = [default_team[0]]

    for table in TABLES_TO_MIGRATE:
        # 1. 添加 team_id 列
        op.add_column(table, sa.Column('team_id', sa.BigInteger(), nullable=True))

        # 2. 为现有数据分配 team_id（取第一个团队）
        first_team_id = team_ids[0]
        op.execute(f"UPDATE {table} SET team_id = {first_team_id} WHERE team_id IS NULL")

        # 3. 复制数据到其他团队
        for other_team_id in team_ids[1:]:
            # 获取表结构，排除 id, team_id, created_time, updated_time
            columns_result = conn.execute(sa.text(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{table}'
                AND COLUMN_NAME NOT IN ('id', 'team_id', 'created_time', 'updated_time')
            """)).fetchall()
            columns = [c[0] for c in columns_result]
            columns_str = ', '.join(columns)

            # 复制数据
            op.execute(f"""
                INSERT INTO {table} ({columns_str}, team_id)
                SELECT {columns_str}, {other_team_id}
                FROM {table}
                WHERE team_id = {first_team_id}
            """)

        # 4. 设置 NOT NULL
        op.alter_column(table, 'team_id', nullable=False)

        # 5. 添加索引
        op.create_index(f'idx_{table}_team_id', table, ['team_id'])


def downgrade() -> None:
    """回滚核心配置表的 team_id"""
    for table in TABLES_TO_MIGRATE:
        # 1. 删除索引
        op.drop_index(f'idx_{table}_team_id', table)

        # 2. 只保留第一个团队的数据，删除其他团队的复制数据
        # 这需要谨慎处理，这里简化处理：保留 team_id 最小的数据
        conn = op.get_bind()
        min_team = conn.execute(sa.text(f"""
            SELECT MIN(team_id) FROM {table}
        """)).fetchone()

        if min_team and min_team[0]:
            op.execute(f"""
                DELETE FROM {table} WHERE team_id > {min_team[0]}
            """)

        # 3. 删除列
        op.drop_column(table, 'team_id')