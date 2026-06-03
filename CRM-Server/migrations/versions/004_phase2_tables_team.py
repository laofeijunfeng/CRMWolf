"""Phase 2: Add team_id to logs and team resource tables

Revision ID: 004_phase2_tables_team
Revises: 003_config_tables_team
Create Date: 2025-05-28

迁移表：
- crm_ai_config（团队资源，复制到各团队）
- crm_conversation_logs（日志，迁移到默认团队）
- crm_contract_approval_records（日志，添加直接 team_id）
- crm_stage_template_change_logs（日志，添加 team_id）
- crm_opportunity_stage_snapshots（快照，添加 team_id）

策略：
- AI Config：复制到各团队（每个团队可独立配置）
- 日志类：迁移到默认团队或添加 team_id（不复制）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004_phase2_tables_team'
down_revision: Union[str, None] = '003_config_tables_team'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 需复制的表（团队资源）
COPY_TABLES = ['crm_ai_config']

# 需迁移的表（日志类）
MIGRATE_TABLES = [
    'crm_conversation_logs',
    'crm_contract_approval_records',
    'crm_stage_template_change_logs',
    'crm_opportunity_stage_snapshots',
]

# 补充缺失的表（应该已有 team_id 但数据库缺失）
SUPPLEMENT_TABLES = [
    'crm_contract_approvals',
]


def upgrade() -> None:
    """为日志和团队资源表添加 team_id"""
    conn = op.get_bind()

    # 获取所有团队
    teams = conn.execute(sa.text("SELECT id FROM teams")).fetchall()
    team_ids = [t[0] for t in teams]

    if not team_ids:
        # 创建默认团队
        conn.execute(sa.text(
            "ALTER TABLE teams MODIFY owner_id INT NULL"
        ))
        conn.execute(sa.text(
            "INSERT INTO teams (name, code, owner_id, parent_id, created_at, updated_at) VALUES ('默认团队', 'DEFAULT', NULL, NULL, NOW(), NOW())"
        ))
        default_team = conn.execute(sa.text("SELECT LAST_INSERT_ID()")).fetchone()
        team_ids = [default_team[0]]

    first_team_id = team_ids[0]

    # === 需复制的表（团队资源）===
    for table in COPY_TABLES:
        # 检查 team_id 列是否已存在
        result = conn.execute(sa.text(f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table}'
            AND COLUMN_NAME = 'team_id'
        """)).fetchone()
        column_exists = result[0] > 0

        if not column_exists:
            # 1. 添加 team_id 列
            op.add_column(table, sa.Column('team_id', sa.BigInteger(), nullable=True))

        # 2. 为现有数据分配 team_id（取第一个团队）
        conn.execute(sa.text(f"UPDATE {table} SET team_id = {first_team_id} WHERE team_id IS NULL"))

        # 3. 复制数据到其他团队（如果有多个团队）
        for other_team_id in team_ids[1:]:
            # AI Config 是单条配置，需要复制
            columns_result = conn.execute(sa.text(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table}'
                AND COLUMN_NAME NOT IN ('id', 'team_id', 'created_at', 'updated_at', 'updated_by')
            """)).fetchall()
            columns = [c[0] for c in columns_result]
            columns_str = ', '.join(columns)

            conn.execute(sa.text(f"""
                INSERT INTO {table} ({columns_str}, team_id)
                SELECT {columns_str}, {other_team_id}
                FROM {table}
                WHERE team_id = {first_team_id}
            """))

        # 4. 设置 NOT NULL（MySQL 需要指定类型）
        conn.execute(sa.text(f"ALTER TABLE {table} MODIFY team_id BIGINT NOT NULL COMMENT '团队ID'"))

        # 5. 添加索引
        result = conn.execute(sa.text(f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table}'
            AND INDEX_NAME = 'idx_{table}_team_id'
        """)).fetchone()
        index_exists = result[0] > 0

        if not index_exists:
            op.create_index(f'idx_{table}_team_id', table, ['team_id'])

    # === 补充缺失的表（应该已有但数据库缺失）===
    for table in SUPPLEMENT_TABLES:
        # 检查 team_id 列是否已存在
        result = conn.execute(sa.text(f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table}'
            AND COLUMN_NAME = 'team_id'
        """)).fetchone()
        column_exists = result[0] > 0

        if not column_exists:
            # 1. 添加 team_id 列
            op.add_column(table, sa.Column('team_id', sa.BigInteger(), nullable=True))

            # 2. 为现有数据分配 team_id
            if table == 'crm_contract_approvals':
                # 通过 contract_id 关联获取 team_id
                conn.execute(sa.text(f"""
                    UPDATE {table} a
                    JOIN crm_contracts c ON a.contract_id = c.id
                    SET a.team_id = c.team_id
                    WHERE a.team_id IS NULL
                """))
            else:
                conn.execute(sa.text(f"UPDATE {table} SET team_id = {first_team_id} WHERE team_id IS NULL"))

            # 3. 设置 NOT NULL
            conn.execute(sa.text(f"ALTER TABLE {table} MODIFY team_id BIGINT NOT NULL COMMENT '团队ID'"))

            # 4. 添加索引
            result = conn.execute(sa.text(f"""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table}'
                AND INDEX_NAME = 'idx_{table}_team_id'
            """)).fetchone()
            index_exists = result[0] > 0

            if not index_exists:
                op.create_index(f'idx_{table}_team_id', table, ['team_id'])

    # === 需迁移的表（日志类）===
    for table in MIGRATE_TABLES:
        # 检查 team_id 列是否已存在
        result = conn.execute(sa.text(f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table}'
            AND COLUMN_NAME = 'team_id'
        """)).fetchone()
        column_exists = result[0] > 0

        if not column_exists:
            # 1. 添加 team_id 列
            op.add_column(table, sa.Column('team_id', sa.BigInteger(), nullable=True))

        # 2. 为现有数据分配 team_id（日志迁移到默认团队）
        # crm_contract_approval_records 可通过 approval_id 获取 team_id
        if table == 'crm_contract_approval_records':
            conn.execute(sa.text(f"""
                UPDATE {table} r
                JOIN crm_contract_approvals a ON r.approval_id = a.id
                SET r.team_id = a.team_id
                WHERE r.team_id IS NULL
            """))
        elif table == 'crm_opportunity_stage_snapshots':
            conn.execute(sa.text(f"""
                UPDATE {table} s
                JOIN crm_opportunities o ON s.opportunity_id = o.id
                SET s.team_id = o.team_id
                WHERE s.team_id IS NULL
            """))
        elif table == 'crm_stage_template_change_logs':
            conn.execute(sa.text(f"""
                UPDATE {table} l
                JOIN crm_procurement_stage_templates t ON l.template_id = t.id
                SET l.team_id = t.team_id
                WHERE l.team_id IS NULL
            """))
        elif table == 'crm_conversation_logs':
            # conversation_logs 可能无法直接关联，迁移到默认团队
            conn.execute(sa.text(f"UPDATE {table} SET team_id = {first_team_id} WHERE team_id IS NULL"))

        # 3. 设置 NOT NULL（MySQL 需要指定类型）
        conn.execute(sa.text(f"ALTER TABLE {table} MODIFY team_id BIGINT NOT NULL COMMENT '团队ID'"))

        # 4. 添加索引
        result = conn.execute(sa.text(f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table}'
            AND INDEX_NAME = 'idx_{table}_team_id'
        """)).fetchone()
        index_exists = result[0] > 0

        if not index_exists:
            op.create_index(f'idx_{table}_team_id', table, ['team_id'])


def downgrade() -> None:
    """回滚日志和团队资源表的 team_id"""
    conn = op.get_bind()

    # 需复制的表：删除其他团队的复制数据
    for table in COPY_TABLES:
        min_team = conn.execute(sa.text(f"""
            SELECT MIN(team_id) FROM {table}
        """)).fetchone()

        if min_team and min_team[0]:
            conn.execute(sa.text(f"""
                DELETE FROM {table} WHERE team_id > {min_team[0]}
            """))

        op.drop_index(f'idx_{table}_team_id', table)
        op.drop_column(table, 'team_id')

    # 需迁移的表：直接删除 team_id
    for table in MIGRATE_TABLES:
        op.drop_index(f'idx_{table}_team_id', table)
        op.drop_column(table, 'team_id')