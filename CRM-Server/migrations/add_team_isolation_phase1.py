"""
团队隔离迁移脚本 - Phase 1: 核心业务配置表

迁移表：
1. crm_opportunity_stages - 销售阶段配置
2. crm_approval_flows - 审批流程模板
3. crm_approval_nodes - 审批节点
4. crm_procurement_methods - 采购方式
5. crm_procurement_stage_templates - 采购阶段模板

策略：配置数据复制到所有现有团队
- 现有配置数据作为模板
- 为每个现有团队复制一份配置数据
- 子表（nodes, templates）需要跟随父表复制，并更新外键引用

运行方式：
  python migrations/add_team_isolation_phase1.py
  python migrations/add_team_isolation_phase1.py --verify
  python migrations/add_team_isolation_phase1.py --rollback
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal, engine


# 表分组
PARENT_TABLES = ["crm_opportunity_stages", "crm_approval_flows", "crm_procurement_methods"]
CHILD_TABLES = ["crm_approval_nodes", "crm_procurement_stage_templates"]

# 依赖关系
CHILD_DEPENDS_ON = {
    "crm_approval_nodes": {"parent": "crm_approval_flows", "fk": "flow_id"},
    "crm_procurement_stage_templates": {"parent": "crm_procurement_methods", "fk": "procurement_method_id"},
}

# ID 映射存储（用于子表外键更新）
id_mappings = {
    "crm_approval_flows": {},      # team_id -> {old_id: new_id}
    "crm_procurement_methods": {}, # team_id -> {old_id: new_id}
}


def get_table_columns(conn, table: str) -> list:
    """获取表的列名列表（排除 id 和 team_id）"""
    result = conn.execute(text(f"SHOW COLUMNS FROM {table}"))
    return [row[0] for row in result.fetchall()]


def copy_parent_table_data(conn, table: str, teams: list) -> dict:
    """
    复制父表数据到每个团队
    返回：team_id -> {old_id: new_id} 的映射
    """
    columns = get_table_columns(conn, table)
    insert_cols = [c for c in columns if c not in ['id', 'team_id']]
    insert_cols.append('team_id')

    mapping = {}

    for team in teams:
        team_id = team[0]
        team_mapping = {}

        # 获取 team_id 为 NULL 的原始数据
        result = conn.execute(text(f"""
            SELECT id, {', '.join(insert_cols[:-1])} FROM {table} WHERE team_id IS NULL
        """))
        rows = result.fetchall()

        if not rows:
            continue

        print(f"  {table}: 复制 {len(rows)} 条到团队 {team_id}")

        for row in rows:
            old_id = row[0]
            values = {col: row[i+1] for i, col in enumerate(insert_cols[:-1])}
            values['team_id'] = team_id

            # 插入新记录
            cols_str = ', '.join(insert_cols)
            vals_str = ', '.join([f':{c}' for c in insert_cols])
            conn.execute(text(f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str})"), values)
            conn.commit()

            # 获取新 ID
            new_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
            team_mapping[old_id] = new_id

        mapping[team_id] = team_mapping

    return mapping


def copy_child_table_data(conn, table: str, teams: list, parent_mapping: dict, fk_col: str):
    """
    复制子表数据，更新外键引用
    """
    columns = get_table_columns(conn, table)
    insert_cols = [c for c in columns if c not in ['id', 'team_id']]
    insert_cols.append('team_id')

    for team in teams:
        team_id = team[0]
        team_mapping = parent_mapping.get(team_id, {})

        if not team_mapping:
            continue

        result = conn.execute(text(f"""
            SELECT id, {', '.join(insert_cols[:-1])} FROM {table} WHERE team_id IS NULL
        """))
        rows = result.fetchall()

        if not rows:
            continue

        print(f"  {table}: 复制 {len(rows)} 条到团队 {team_id}")

        for row in rows:
            old_id = row[0]
            values = {}
            for i, col in enumerate(insert_cols[:-1]):
                val = row[i+1]
                # 更新外键
                if col == fk_col and val in team_mapping:
                    val = team_mapping[val]
                values[col] = val
            values['team_id'] = team_id

            cols_str = ', '.join(insert_cols)
            vals_str = ', '.join([f':{c}' for c in insert_cols])
            conn.execute(text(f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str})"), values)
            conn.commit()


def upgrade():
    """执行迁移"""
    try:
        print("=" * 60)
        print("Phase 1: 核心业务配置表团队隔离迁移")
        print("=" * 60)

        # Step 1: 获取所有团队
        print("\n[Step 1] 获取现有团队...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT id, name FROM teams ORDER BY id"))
            teams = result.fetchall()
            if not teams:
                print("  ⚠ 没有团队，跳过迁移")
                return
            print(f"  ✓ 发现 {len(teams)} 个团队:")
            for t in teams:
                print(f"    - id={t[0]}, name={t[1]}")

        # Step 2: 添加 team_id 列
        print("\n[Step 2] 添加 team_id 列...")
        all_tables = PARENT_TABLES + CHILD_TABLES
        for table in all_tables:
            with engine.connect() as conn:
                result = conn.execute(text(f"SHOW COLUMNS FROM {table} LIKE 'team_id'"))
                if result.fetchone():
                    print(f"  ✓ {table} 已有 team_id")
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN team_id BIGINT NULL COMMENT '团队ID'"))
                conn.commit()
                print(f"  ✓ {table} 添加 team_id")

        # Step 3: 复制父表数据
        print("\n[Step 3] 复制父表数据...")
        for table in PARENT_TABLES:
            with engine.connect() as conn:
                mapping = copy_parent_table_data(conn, table, teams)
                if table in id_mappings:
                    id_mappings[table] = mapping

        # Step 4: 复制子表数据
        print("\n[Step 4] 复制子表数据...")
        for table in CHILD_TABLES:
            dep = CHILD_DEPENDS_ON[table]
            parent_table = dep['parent']
            fk_col = dep['fk']

            with engine.connect() as conn:
                copy_child_table_data(conn, table, teams, id_mappings[parent_table], fk_col)

        # Step 5: 添加索引
        print("\n[Step 5] 添加索引...")
        for table in all_tables:
            idx_name = f"idx_{table}_team_id"
            with engine.connect() as conn:
                result = conn.execute(text(f"SHOW INDEX FROM {table} WHERE Key_name = '{idx_name}'"))
                if not result.fetchone():
                    conn.execute(text(f"CREATE INDEX {idx_name} ON {table} (team_id)"))
                    conn.commit()
                    print(f"  ✓ {table} 索引已创建")

        # Step 6: 保留原有 NULL 数据
        print("\n[Step 6] 原有数据作为模板保留...")
        print("  ✓ 原 team_id=NULL 的数据保留为系统默认模板")

        print("\n" + "=" * 60)
        print("Phase 1 迁移完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        raise


def downgrade():
    """回滚迁移"""
    try:
        print("=" * 60)
        print("回滚 Phase 1")
        print("=" * 60)

        all_tables = PARENT_TABLES + CHILD_TABLES

        with engine.connect() as conn:
            # 删除复制的数据
            print("\n[Step 1] 删除复制数据...")
            for table in all_tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE team_id IS NOT NULL"))
                count = result.scalar()
                if count > 0:
                    conn.execute(text(f"DELETE FROM {table} WHERE team_id IS NOT NULL"))
                    conn.commit()
                    print(f"  ✓ {table}: 删除 {count} 条")

            # 删除索引
            print("\n[Step 2] 删除索引...")
            for table in all_tables:
                idx_name = f"idx_{table}_team_id"
                result = conn.execute(text(f"SHOW INDEX FROM {table} WHERE Key_name = '{idx_name}'"))
                if result.fetchone():
                    conn.execute(text(f"DROP INDEX {idx_name} ON {table}"))
                    conn.commit()
                    print(f"  ✓ {table} 索引已删除")

            # 删除列
            print("\n[Step 3] 删除 team_id 列...")
            for table in all_tables:
                result = conn.execute(text(f"SHOW COLUMNS FROM {table} LIKE 'team_id'"))
                if result.fetchone():
                    conn.execute(text(f"ALTER TABLE {table} DROP COLUMN team_id"))
                    conn.commit()
                    print(f"  ✓ {table} 列已删除")

        print("\n" + "=" * 60)
        print("回滚完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 回滚失败: {e}")


def verify_migration(db):
    """验证迁移结果"""
    errors = []
    all_tables = PARENT_TABLES + CHILD_TABLES

    print("\n" + "=" * 60)
    print("验证迁移结果")
    print("=" * 60)

    for table in all_tables:
        print(f"\n[{table}]")

        # 检查列
        result = db.execute(text(f"SHOW COLUMNS FROM {table} LIKE 'team_id'"))
        if result.fetchone():
            print("  ✓ team_id 列存在")
        else:
            errors.append(f"{table} 缺少 team_id")
            print("  ✗ team_id 列缺失")

        # 检查索引
        result = db.execute(text(f"SHOW INDEX FROM {table} WHERE Key_name = 'idx_{table}_team_id'"))
        if result.fetchone():
            print("  ✓ 索引存在")
        else:
            errors.append(f"{table} 缺少索引")

        # 数据分布
        result = db.execute(text(f"SELECT team_id, COUNT(*) FROM {table} GROUP BY team_id ORDER BY team_id"))
        for row in result.fetchall():
            tid = "NULL(模板)" if row[0] is None else row[0]
            print(f"  team_id={tid}: {row[1]} 条")

    if errors:
        print("\n❌ 验证失败:", errors)
        return False
    print("\n✅ 验证成功")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    if args.verify:
        db = SessionLocal()
        verify_migration(db)
        db.close()
    elif args.rollback:
        downgrade()
    else:
        upgrade()
        db = SessionLocal()
        verify_migration(db)
        db.close()