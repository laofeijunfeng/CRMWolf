"""回填存量客户的 account_name_norm 字段（Phase 1.4）

执行前提：
1. 已执行 migrations/001_add_name_norm_column.sql
2. account_name_norm 列已存在
3. pg_trgm 扩展已安装

执行：
python3 scripts/backfill_name_norm.py
"""

import sys
import os

# 添加项目根目录到 Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models.customer import Customer
from app.utils.name_normalizer import normalize_corp_name


def backfill_name_norm(db: Session):
    """回填存量客户的 account_name_norm"""
    try:
        # 查询所有 account_name_norm 为空的客户
        customers = db.query(Customer).filter(
            Customer.account_name_norm.is_(None),
            Customer.account_name.isnot(None)
        ).all()

        total = len(customers)
        print(f"找到 {total} 条待回填客户记录")

        updated = 0
        for customer in customers:
            customer.account_name_norm = normalize_corp_name(customer.account_name)
            updated += 1

            # 每 100 条提交一次
            if updated % 100 == 0:
                db.commit()
                print(f"已回填 {updated}/{total} 条记录")

        # 最终提交
        db.commit()
        print(f"✅ 回填完成，共更新 {updated} 条记录")

    except Exception as e:
        db.rollback()
        print(f"❌ 回填失败: {e}")
        raise


def main():
    """主函数"""
    print("=" * 50)
    print("存量客户 account_name_norm 回填脚本")
    print("=" * 50)

    # 检查列是否存在
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = inspector.get_columns('crm_customers')
        if 'account_name_norm' not in [col['name'] for col in columns]:
            print("❌ account_name_norm 列不存在，请先执行 migrations/001_add_name_norm_column.sql")
            sys.exit(1)
        print("✅ account_name_norm 列存在")
    except Exception as e:
        print(f"❌ 检查数据库失败: {e}")
        sys.exit(1)

    # 执行回填
    db = SessionLocal()
    try:
        backfill_name_norm(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()