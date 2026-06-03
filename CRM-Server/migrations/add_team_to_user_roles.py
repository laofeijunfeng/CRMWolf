"""
团队隔离迁移脚本 - Phase 0: 权限系统 user_roles 表

功能：
1. 为 user_roles 表添加 team_id 字段
2. 迁移现有数据（根据用户所属团队设置 team_id）
3. 更新唯一约束为 (user_id, team_id, role_id)

策略：
- 用户只属于一个团队：直接使用该 team_id
- 用户属于多个团队：使用当前活跃团队（current_team=True）

运行方式：
  python migrations/add_team_to_user_roles.py          # 执行迁移
  python migrations/add_team_to_user_roles.py --verify # 验证迁移结果
  python migrations/add_team_to_user_roles.py --rollback # 回滚迁移
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal, engine


def upgrade():
    """执行迁移"""
    db = SessionLocal()
    try:
        print("=" * 60)
        print("Phase 0: user_roles 表团队隔离迁移")
        print("=" * 60)

        # Step 1: 检查并添加 team_id 列
        print("\n[Step 1] 添加 team_id 列...")
        with engine.connect() as conn:
            result = conn.execute(text("SHOW COLUMNS FROM user_roles LIKE 'team_id'"))
            if result.fetchone():
                print("  ✓ team_id 列已存在，跳过")
            else:
                conn.execute(text("""
                    ALTER TABLE user_roles
                    ADD COLUMN team_id BIGINT NULL COMMENT '团队ID'
                """))
                conn.commit()
                print("  ✓ team_id 列已添加（暂为 NULL）")

        # Step 2: 迁移现有数据
        print("\n[Step 2] 迁移现有数据...")
        with engine.connect() as conn:
            # 检查是否有需要迁移的数据
            result = conn.execute(text("""
                SELECT COUNT(*) FROM user_roles WHERE team_id IS NULL
            """))
            null_count = result.scalar()
            print(f"  发现 {null_count} 条需要迁移的记录")

            if null_count > 0:
                # 策略1: 用户只有一个团队，直接使用
                conn.execute(text("""
                    UPDATE user_roles ur
                    JOIN (
                        SELECT user_id, team_id
                        FROM user_teams
                        GROUP BY user_id
                        HAVING COUNT(*) = 1
                    ) single_team ON ur.user_id = single_team.user_id
                    SET ur.team_id = single_team.team_id
                    WHERE ur.team_id IS NULL
                """))
                conn.commit()
                print("  ✓ 单团队用户数据已迁移")

                # 策略2: 用户有多个团队，使用当前活跃团队
                conn.execute(text("""
                    UPDATE user_roles ur
                    JOIN user_teams ut ON ur.user_id = ut.user_id AND ut.current_team = 1
                    SET ur.team_id = ut.team_id
                    WHERE ur.team_id IS NULL
                """))
                conn.commit()
                print("  ✓ 多团队用户数据已迁移（使用当前活跃团队）")

                # 检查是否还有未迁移的数据
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM user_roles WHERE team_id IS NULL
                """))
                remaining = result.scalar()
                if remaining > 0:
                    print(f"  ⚠ 仍有 {remaining} 条记录无法迁移（用户无团队）")
                    # 获取默认团队或创建一个
                    result = conn.execute(text("SELECT id FROM teams ORDER BY id LIMIT 1"))
                    default_team = result.scalar()
                    if default_team:
                        conn.execute(text("""
                            UPDATE user_roles SET team_id = :team_id WHERE team_id IS NULL
                        """), {"team_id": default_team})
                        conn.commit()
                        print(f"  ✓ 未关联团队的记录已设置到默认团队 (id={default_team})")

        # Step 3: 设置 team_id NOT NULL
        print("\n[Step 3] 设置 team_id NOT NULL...")
        with engine.connect() as conn:
            # 先检查是否还有 NULL 值
            result = conn.execute(text("SELECT COUNT(*) FROM user_roles WHERE team_id IS NULL"))
            if result.scalar() > 0:
                print("  ⚠ 存在 NULL 值，无法设置 NOT NULL")
                print("  请手动处理这些记录后再运行")
                return

            conn.execute(text("""
                ALTER TABLE user_roles
                MODIFY COLUMN team_id BIGINT NOT NULL COMMENT '团队ID'
            """))
            conn.commit()
            print("  ✓ team_id 已设置为 NOT NULL")

        # Step 4: 删除旧唯一约束（如果有），添加新约束
        print("\n[Step 4] 更新唯一约束...")
        with engine.connect() as conn:
            # 检查是否存在旧的唯一约束（user_id + role_id）
            result = conn.execute(text("""
                SELECT CONSTRAINT_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'user_roles'
                AND CONSTRAINT_TYPE = 'UNIQUE'
            """))
            old_constraints = result.fetchall()

            for constraint in old_constraints:
                constraint_name = constraint[0]
                if constraint_name != 'uq_user_role_team':
                    conn.execute(text(f"""
                        ALTER TABLE user_roles DROP INDEX {constraint_name}
                    """))
                    conn.commit()
                    print(f"  ✓ 删除旧约束: {constraint_name}")

            # 添加新唯一约束
            result = conn.execute(text("""
                SELECT CONSTRAINT_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'user_roles'
                AND CONSTRAINT_NAME = 'uq_user_role_team'
            """))
            if not result.fetchone():
                conn.execute(text("""
                    ALTER TABLE user_roles
                    ADD CONSTRAINT uq_user_role_team
                    UNIQUE (user_id, team_id, role_id)
                """))
                conn.commit()
                print("  ✓ 新唯一约束已添加: (user_id, team_id, role_id)")
            else:
                print("  ✓ 新唯一约束已存在")

        # Step 5: 添加索引
        print("\n[Step 5] 添加索引...")
        with engine.connect() as conn:
            result = conn.execute(text("""
                SHOW INDEX FROM user_roles WHERE Key_name = 'idx_user_roles_team_id'
            """))
            if not result.fetchone():
                conn.execute(text("""
                    CREATE INDEX idx_user_roles_team_id ON user_roles (team_id)
                """))
                conn.commit()
                print("  ✓ 索引 idx_user_roles_team_id 已创建")
            else:
                print("  ✓ 索引已存在")

        print("\n" + "=" * 60)
        print("Phase 0 迁移完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def downgrade():
    """回滚迁移"""
    db = SessionLocal()
    try:
        print("=" * 60)
        print("回滚 Phase 0: user_roles 表迁移")
        print("=" * 60)

        with engine.connect() as conn:
            # 删除索引
            print("\n[Step 1] 删除索引...")
            result = conn.execute(text("""
                SHOW INDEX FROM user_roles WHERE Key_name = 'idx_user_roles_team_id'
            """))
            if result.fetchone():
                conn.execute(text("DROP INDEX idx_user_roles_team_id ON user_roles"))
                conn.commit()
                print("  ✓ 索引已删除")

            # 删除唯一约束
            print("\n[Step 2] 删除唯一约束...")
            result = conn.execute(text("""
                SELECT CONSTRAINT_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'user_roles'
                AND CONSTRAINT_NAME = 'uq_user_role_team'
            """))
            if result.fetchone():
                conn.execute(text("ALTER TABLE user_roles DROP INDEX uq_user_role_team"))
                conn.commit()
                print("  ✓ 唯一约束已删除")

            # 删除 team_id 列
            print("\n[Step 3] 删除 team_id 列...")
            result = conn.execute(text("SHOW COLUMNS FROM user_roles LIKE 'team_id'"))
            if result.fetchone():
                conn.execute(text("ALTER TABLE user_roles DROP COLUMN team_id"))
                conn.commit()
                print("  ✓ team_id 列已删除")

            # 重新添加旧的唯一约束（如果需要）
            print("\n[Step 4] 重建旧唯一约束...")
            conn.execute(text("""
                ALTER TABLE user_roles
                ADD CONSTRAINT uq_user_role UNIQUE (user_id, role_id)
            """))
            conn.commit()
            print("  ✓ 旧唯一约束已重建: (user_id, role_id)")

        print("\n" + "=" * 60)
        print("回滚完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 回滚失败: {e}")
        db.rollback()
    finally:
        db.close()


def verify_migration(db):
    """验证迁移结果"""
    errors = []

    print("\n" + "=" * 60)
    print("验证迁移结果")
    print("=" * 60)

    # 检查列
    print("\n[检查] team_id 列...")
    result = db.execute(text("SHOW COLUMNS FROM user_roles LIKE 'team_id'"))
    col = result.fetchone()
    if col:
        col_info = list(col)
        print(f"  ✓ 列存在: {col_info}")
        if 'NO' not in str(col_info[2]):  # Null 字段
            errors.append("team_id 列应为 NOT NULL")
            print("  ✗ 列应为 NOT NULL")
        else:
            print("  ✓ 列为 NOT NULL")
    else:
        errors.append("team_id 列不存在")
        print("  ✗ 列不存在")

    # 检查索引
    print("\n[检查] team_id 索引...")
    result = db.execute(text("""
        SHOW INDEX FROM user_roles WHERE Key_name = 'idx_user_roles_team_id'
    """))
    if result.fetchone():
        print("  ✓ 索引 idx_user_roles_team_id 存在")
    else:
        errors.append("索引 idx_user_roles_team_id 不存在")
        print("  ✗ 索引不存在")

    # 检查唯一约束
    print("\n[检查] 唯一约束...")
    result = db.execute(text("""
        SELECT CONSTRAINT_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION)
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'user_roles'
        AND CONSTRAINT_NAME = 'uq_user_role_team'
        GROUP BY CONSTRAINT_NAME
    """))
    constraint = result.fetchone()
    if constraint:
        columns = constraint[1]
        print(f"  ✓ 唯一约束存在: {constraint[0]} ({columns})")
        expected_cols = 'user_id,team_id,role_id'
        if columns != expected_cols:
            errors.append(f"唯一约束列应为 {expected_cols}，实际为 {columns}")
            print(f"  ✗ 约束列不正确: {columns}")
    else:
        errors.append("唯一约束 uq_user_role_team 不存在")
        print("  ✗ 唯一约束不存在")

    # 检查数据
    print("\n[检查] 数据完整性...")
    result = db.execute(text("SELECT COUNT(*) FROM user_roles WHERE team_id IS NULL"))
    null_count = result.scalar()
    if null_count == 0:
        print(f"  ✓ 所有记录都有 team_id")
    else:
        errors.append(f"{null_count} 条记录 team_id 为 NULL")
        print(f"  ✗ {null_count} 条记录 team_id 为 NULL")

    # 检查数据分布
    print("\n[检查] 数据分布...")
    result = db.execute(text("""
        SELECT team_id, COUNT(*) as count
        FROM user_roles
        GROUP BY team_id
        ORDER BY team_id
    """))
    distribution = result.fetchall()
    print("  team_id 分布:")
    for row in distribution:
        print(f"    - team_id={row[0]}: {row[1]} 条")

    if errors:
        print("\n" + "=" * 60)
        print("❌ 验证失败:")
        for error in errors:
            print(f"  - {error}")
        print("=" * 60)
        return False
    else:
        print("\n" + "=" * 60)
        print("✅ 验证成功")
        print("=" * 60)
        return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="user_roles 表团队隔离迁移")
    parser.add_argument("--verify", action="store_true", help="仅验证迁移结果")
    parser.add_argument("--rollback", action="store_true", help="回滚迁移")
    args = parser.parse_args()

    if args.verify:
        db = SessionLocal()
        verify_migration(db)
        db.close()
    elif args.rollback:
        downgrade()
    else:
        upgrade()
        # 迁移后自动验证
        db = SessionLocal()
        verify_migration(db)
        db.close()