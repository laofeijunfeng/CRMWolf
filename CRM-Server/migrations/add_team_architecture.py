"""
团队架构迁移脚本

功能：
1. 创建 teams 表
2. 创建 user_teams 关联表（多团队模式）
3. 创建默认团队 DEFAULT_TEAM
4. 添加 team_id 列到所有业务表
5. 迁移现有数据到默认团队
6. 将所有用户绑定到默认团队
7. 添加索引

运行方式：
  python migrations/add_team_architecture.py          # 执行迁移
  python migrations/add_team_architecture.py --verify # 验证迁移结果
"""
import sys
import random
import string
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal, engine, Base
from app.models.team import Team, UserTeam


# 需要添加 team_id 的业务表
BUSINESS_TABLES = [
    "crm_leads",
    "crm_customers",
    "crm_contacts",
    "crm_lead_follow_ups",
    "crm_customer_follow_ups",
    "crm_opportunities",
    "crm_contracts",
    "crm_contract_payment_plans",
    "crm_payment_records",
    "crm_invoice_titles",
    "crm_invoice_applications",
    "crm_operation_logs",
]

# 需要添加索引的表
TABLES_WITH_INDEX = [
    "crm_leads",
    "crm_customers",
    "crm_contacts",
    "crm_opportunities",
    "crm_contracts",
    "crm_contract_payment_plans",
    "crm_payment_records",
    "crm_invoice_titles",
    "crm_invoice_applications",
    "crm_operation_logs",
]


def generate_invite_code(length=8):
    """生成随机邀请码"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def create_team_tables():
    """创建 teams 和 user_teams 表"""
    print("\n=== 创建团队表 ===")

    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            UserTeam.__table__
        ]
    )

    print("✓ teams 表创建成功")
    print("✓ user_teams 表创建成功")


def create_default_team(db):
    """创建默认团队"""
    print("\n=== 创建默认团队 ===")

    # 检查是否已有团队
    result = db.execute(text("SELECT COUNT(*) FROM teams"))
    existing_count = result.scalar()
    if existing_count > 0:
        print(f"⚠️  已存在 {existing_count} 个团队，跳过创建")
        result = db.execute(text("SELECT id FROM teams LIMIT 1"))
        return result.scalar()

    # 获取第一个用户作为默认团队创建者
    result = db.execute(text("SELECT id FROM users ORDER BY id LIMIT 1"))
    first_user_id = result.scalar()

    if not first_user_id:
        print("⚠️  用户表为空，无法创建默认团队")
        return None

    invite_code = generate_invite_code()

    db.execute(text("""
        INSERT INTO teams (name, code, owner_id, parent_id, created_at, updated_at)
        VALUES ('DEFAULT_TEAM', :code, :owner_id, NULL, NOW(), NOW())
    """), {"code": invite_code, "owner_id": first_user_id})

    result = db.execute(text("SELECT id FROM teams WHERE name = 'DEFAULT_TEAM'"))
    team_id = result.scalar()

    print(f"✓ 默认团队创建成功，ID: {team_id}, 邀请码: {invite_code}")
    return team_id


def add_team_id_columns():
    """添加 team_id 列到业务表"""
    print("\n=== 添加 team_id 列到业务表 ===")

    with engine.connect() as conn:
        for table in BUSINESS_TABLES:
            try:
                # 先检查列是否已存在
                result = conn.execute(text(f"SHOW COLUMNS FROM {table} LIKE 'team_id'"))
                if result.fetchone():
                    print(f"  ⚠️  {table} 已有 team_id 列，跳过")
                    continue

                # 添加列（先 nullable）
                conn.execute(text(f"""
                    ALTER TABLE {table}
                    ADD COLUMN team_id BIGINT NULL COMMENT '团队ID'
                """))
                conn.commit()
                print(f"  ✓ {table} 添加 team_id 列成功")
            except Exception as e:
                print(f"  ✗ {table} 添加列失败: {e}")
                raise


def migrate_data_to_default_team(db, team_id):
    """将现有数据迁移到默认团队"""
    print("\n=== 迁移现有数据到默认团队 ===")

    if not team_id:
        print("⚠️  无默认团队 ID，跳过数据迁移")
        return

    for table in BUSINESS_TABLES:
        try:
            # 更新所有 team_id 为 NULL 的记录
            result = db.execute(text(f"""
                UPDATE {table}
                SET team_id = :team_id
                WHERE team_id IS NULL
            """), {"team_id": team_id})

            count = result.rowcount
            print(f"  ✓ {table} 迁移 {count} 条记录到默认团队")
        except Exception as e:
            print(f"  ✗ {table} 数据迁移失败: {e}")
            raise


def set_team_id_not_null():
    """设置 team_id 为 NOT NULL"""
    print("\n=== 设置 team_id 为 NOT NULL ===")

    with engine.connect() as conn:
        for table in BUSINESS_TABLES:
            try:
                conn.execute(text(f"""
                    ALTER TABLE {table}
                    MODIFY COLUMN team_id BIGINT NOT NULL COMMENT '团队ID'
                """))
                conn.commit()
                print(f"  ✓ {table} team_id 设置为 NOT NULL")
            except Exception as e:
                print(f"  ✗ {table} 设置 NOT NULL 失败: {e}")
                raise


def add_indexes():
    """添加索引"""
    print("\n=== 添加索引 ===")

    with engine.connect() as conn:
        for table in TABLES_WITH_INDEX:
            index_name = f"idx_{table}_team_id"
            try:
                # 检查索引是否已存在
                result = conn.execute(text(f"SHOW INDEX FROM {table} WHERE Key_name = '{index_name}'"))
                if result.fetchone():
                    print(f"  ⚠️  {table} 已有索引 {index_name}，跳过")
                    continue

                conn.execute(text(f"""
                    CREATE INDEX {index_name} ON {table} (team_id)
                """))
                conn.commit()
                print(f"  ✓ {table} 添加索引 {index_name} 成功")
            except Exception as e:
                print(f"  ✗ {table} 添加索引失败: {e}")
                raise


def bind_users_to_default_team(db, team_id):
    """将所有用户绑定到默认团队"""
    print("\n=== 绑定用户到默认团队 ===")

    if not team_id:
        print("⚠️  无默认团队 ID，跳过用户绑定")
        return

    # 检查是否已有绑定
    result = db.execute(text("SELECT COUNT(*) FROM user_teams"))
    existing_count = result.scalar()
    if existing_count > 0:
        print(f"⚠️  已存在 {existing_count} 条用户-团队绑定，跳过")
        return

    # 获取所有用户
    result = db.execute(text("SELECT id FROM users"))
    users = result.fetchall()

    for user in users:
        user_id = user[0]
        db.execute(text("""
            INSERT INTO user_teams (user_id, team_id, current_team, joined_at)
            VALUES (:user_id, :team_id, TRUE, NOW())
        """), {"user_id": user_id, "team_id": team_id})

    print(f"✓ 绑定 {len(users)} 个用户到默认团队")


def verify_migration(db):
    """验证迁移结果"""
    print("\n=== 验证迁移结果 ===")

    errors = []

    # 1. 检查 teams 表
    result = db.execute(text("SELECT COUNT(*) FROM teams"))
    team_count = result.scalar()
    if team_count == 0:
        errors.append("teams 表无数据")
    else:
        print(f"✓ teams 表: {team_count} 条记录")

    # 2. 检查 user_teams 表
    result = db.execute(text("SELECT COUNT(*) FROM user_teams"))
    user_team_count = result.scalar()
    if user_team_count == 0:
        errors.append("user_teams 表无数据")
    else:
        print(f"✓ user_teams 表: {user_team_count} 条记录")

    # 3. 检查业务表 team_id 列
    for table in BUSINESS_TABLES:
        result = db.execute(text(f"SHOW COLUMNS FROM {table} LIKE 'team_id'"))
        if not result.fetchone():
            errors.append(f"{table} 缺少 team_id 列")
        else:
            # 检查是否有 NULL 值
            result = db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE team_id IS NULL"))
            null_count = result.scalar()
            if null_count > 0:
                errors.append(f"{table} 有 {null_count} 条 team_id=NULL 的记录")
            else:
                print(f"✓ {table}: team_id 列存在，无 NULL 值")

    # 4. 检查索引
    for table in TABLES_WITH_INDEX:
        index_name = f"idx_{table}_team_id"
        result = db.execute(text(f"SHOW INDEX FROM {table} WHERE Key_name = '{index_name}'"))
        if not result.fetchone():
            errors.append(f"{table} 缺少索引 {index_name}")
        else:
            print(f"✓ {table}: 索引 {index_name} 存在")

    if errors:
        print("\n❌ 验证失败:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✅ 验证成功，所有迁移步骤已完成")


def run_migration():
    """执行完整迁移流程"""
    print("=" * 50)
    print("CRMWolf 团队架构迁移")
    print("=" * 50)

    db = SessionLocal()

    try:
        # 1. 创建表
        create_team_tables()

        # 2. 创建默认团队
        team_id = create_default_team(db)

        # 3. 添加列
        add_team_id_columns()

        # 4. 迁移数据
        migrate_data_to_default_team(db, team_id)

        # 5. 设置 NOT NULL
        set_team_id_not_null()

        # 6. 添加索引
        add_indexes()

        # 7. 绑定用户
        bind_users_to_default_team(db, team_id)

        # 8. 提交
        db.commit()

        # 9. 验证
        verify_migration(db)

        print("\n" + "=" * 50)
        print("迁移完成！")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="团队架构迁移脚本")
    parser.add_argument("--verify", action="store_true", help="仅验证迁移结果")
    args = parser.parse_args()

    if args.verify:
        db = SessionLocal()
        verify_migration(db)
        db.close()
    else:
        run_migration()