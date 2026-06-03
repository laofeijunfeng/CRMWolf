"""
客户档案 AI 自动补充字段迁移脚本

功能：
1. 为 crm_customers 表添加客户档案相关字段
2. 添加档案生成状态字段

运行方式：
  python migrations/add_customer_profile_fields.py          # 执行迁移
  python migrations/add_customer_profile_fields.py --verify # 验证迁移结果
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal, engine


def add_profile_fields():
    """添加客户档案字段"""
    print("\n=== 添加客户档案字段 ===")

    fields = [
        ("company_background", "TEXT NULL COMMENT '企业背景（AI生成）'"),
        ("company_website", "VARCHAR(500) NULL COMMENT '公司官网（AI生成）'"),
        ("main_business", "TEXT NULL COMMENT '主营业务（AI生成）'"),
        ("similar_customers", "TEXT NULL COMMENT '同行业客户列表（JSON格式，AI生成）'"),
        ("project_background", "TEXT NULL COMMENT '项目需求背景（从线索跟进记录分析生成）'"),
        ("profile_status", "VARCHAR(20) NULL DEFAULT 'PENDING' COMMENT '档案生成状态：PENDING/GENERATING/COMPLETED/FAILED'"),
        ("profile_generated_time", "DATETIME NULL COMMENT '档案生成完成时间'"),
        ("profile_error_message", "VARCHAR(500) NULL COMMENT '档案生成失败原因'"),
    ]

    with engine.connect() as conn:
        for field_name, field_def in fields:
            try:
                result = conn.execute(text(f"SHOW COLUMNS FROM crm_customers LIKE '{field_name}'"))
                if result.fetchone():
                    print(f"  ⚠️  {field_name} 列已存在，跳过")
                else:
                    conn.execute(text(f"ALTER TABLE crm_customers ADD COLUMN {field_name} {field_def}"))
                    conn.commit()
                    print(f"  ✓ {field_name} 列添加成功")
            except Exception as e:
                print(f"  ✗ 添加 {field_name} 失败: {e}")
                raise


def verify_migration(db):
    """验证迁移结果"""
    print("\n=== 验证迁移结果 ===")

    fields = [
        "company_background",
        "company_website",
        "main_business",
        "similar_customers",
        "project_background",
        "profile_status",
        "profile_generated_time",
        "profile_error_message"
    ]

    errors = []
    for field in fields:
        result = db.execute(text(f"SHOW COLUMNS FROM crm_customers LIKE '{field}'"))
        if not result.fetchone():
            errors.append(f"crm_customers 缺少 {field} 列")
        else:
            print(f"  ✓ {field} 列存在")

    if errors:
        print("\n❌ 验证失败:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✅ 验证成功，所有迁移步骤已完成")


def run_migration():
    """执行完整迁移流程"""
    print("=" * 50)
    print("CRMWolf 客户档案字段迁移")
    print("=" * 50)

    db = SessionLocal()

    try:
        add_profile_fields()
        verify_migration(db)
        print("\n" + "=" * 50)
        print("迁移完成！")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="客户档案字段迁移脚本")
    parser.add_argument("--verify", action="store_true", help="仅验证迁移结果")
    args = parser.parse_args()

    if args.verify:
        db = SessionLocal()
        verify_migration(db)
        db.close()
    else:
        run_migration()