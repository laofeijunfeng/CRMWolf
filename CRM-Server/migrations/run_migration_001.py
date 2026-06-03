"""数据库迁移脚本：添加 account_name_norm 列（MySQL 版本）

执行前提：数据库连接正常（.env 配置正确）

执行：
python3 migrations/run_migration_001.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine
from app.utils.name_normalizer import normalize_corp_name


def run_migration():
    """执行迁移"""
    print("=" * 60)
    print("迁移 001: 添加 account_name_norm 列")
    print("=" * 60)

    with engine.connect() as conn:
        # 检查列是否已存在
        result = conn.execute(text("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'crm_customers'
            AND COLUMN_NAME = 'account_name_norm'
        """))
        exists = result.fetchone()[0] > 0

        if exists:
            print("✅ account_name_norm 列已存在，跳过迁移")
            return

        print("开始迁移...")

        # 1. 添加列
        conn.execute(text("""
            ALTER TABLE crm_customers
            ADD COLUMN account_name_norm VARCHAR(255) COMMENT '归一化客户名称（去后缀/括号）'
        """))
        conn.commit()
        print("✅ 已添加 account_name_norm 列")

        # 2. 创建索引
        try:
            conn.execute(text("""
                CREATE INDEX idx_account_name_norm ON crm_customers (account_name_norm)
            """))
            conn.commit()
            print("✅ 已创建 idx_account_name_norm 索引")
        except Exception as e:
            print(f"⚠️ 索引创建失败（可能已存在）: {e}")

        # 3. 创建前缀索引
        try:
            conn.execute(text("""
                CREATE INDEX idx_account_name_norm_prefix ON crm_customers (account_name_norm(20))
            """))
            conn.commit()
            print("✅ 已创建前缀索引")
        except Exception as e:
            print(f"⚠️ 前缀索引创建失败（MySQL 版本限制）: {e}")

        # 4. 回填存量数据
        print("回填存量数据...")
        result = conn.execute(text("""
            SELECT id, account_name FROM crm_customers
            WHERE account_name IS NOT NULL
        """))
        customers = result.fetchall()

        updated = 0
        for customer_id, account_name in customers:
            name_norm = normalize_corp_name(account_name)
            conn.execute(text("""
                UPDATE crm_customers SET account_name_norm = :name_norm WHERE id = :id
            """), {"name_norm": name_norm, "id": customer_id})
            updated += 1

            if updated % 100 == 0:
                conn.commit()
                print(f"已回填 {updated} 条记录")

        conn.commit()
        print(f"✅ 回填完成，共更新 {updated} 条记录")

    print("=" * 60)
    print("迁移完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)