#!/usr/bin/env python3
"""
清理业务数据脚本

用途：
1. 清空所有业务数据表（线索、客户、商机、合同等）
2. 清空用户表（保留系统角色和权限）
3. 为邮箱认证系统重新注册做准备

使用方式：
    python scripts/cleanup_business_data.py [--confirm]

注意：
- 必须加 --confirm 参数才会真正执行删除
- 不加参数时仅显示将要删除的数据统计
"""

import sys
import os
from argparse import ArgumentParser

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal


# 要清理的业务数据表（按依赖顺序）
BUSINESS_TABLES = [
    "operation_logs",
    "approval_records",
    "approvals",
    "payment_records",
    "payment_plans",
    "invoice_applications",
    "invoice_titles",
    "contracts",
    "opportunities",
    "customer_follow_ups",
    "contacts",
    "customers",
    "lead_follow_ups",
    "leads",
]

# 用户相关表
USER_TABLES = [
    "user_roles",
    "users",
]

# 验证码表（清理过期验证码）
VERIFICATION_TABLES = [
    "email_verification_codes",
]


def count_records(db, table_name: str) -> int:
    """统计表中的记录数"""
    try:
        result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar() or 0
    except Exception as e:
        print(f"  警告：无法统计 {table_name}: {e}")
        return 0


def truncate_table(db, table_name: str) -> bool:
    """清空表（TRUNCATE）"""
    try:
        # 禁用外键检查以避免约束错误
        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        db.execute(text(f"TRUNCATE TABLE {table_name}"))
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        db.commit()
        return True
    except Exception as e:
        print(f"  错误：清空 {table_name} 失败: {e}")
        db.rollback()
        return False


def delete_expired_codes(db) -> int:
    """删除过期验证码"""
    try:
        result = db.execute(text("""
            DELETE FROM email_verification_codes
            WHERE expires_at < NOW() OR used = true
        """))
        db.commit()
        return result.rowcount
    except Exception as e:
        print(f"  错误：清理验证码失败: {e}")
        db.rollback()
        return 0


def show_statistics(db, confirm: bool = False):
    """显示数据统计"""
    print("\n" + "=" * 60)
    print("CRMWolf 数据清理脚本")
    print("=" * 60)

    if not confirm:
        print("\n【统计模式】以下数据将被清理（使用 --confirm 确认执行）:")
    else:
        print("\n【执行模式】正在清理数据...")

    # 业务数据统计
    print("\n业务数据表:")
    total_business = 0
    for table in BUSINESS_TABLES:
        count = count_records(db, table)
        total_business += count
        status = "✓ 已清空" if confirm and truncate_table(db, table) else f"{count} 条"
        print(f"  {table}: {status}")

    # 用户数据统计
    print("\n用户数据表:")
    total_users = 0
    for table in USER_TABLES:
        count = count_records(db, table)
        total_users += count
        status = "✓ 已清空" if confirm and truncate_table(db, table) else f"{count} 条"
        print(f"  {table}: {status}")

    # 验证码清理
    print("\n验证码表:")
    count = count_records(db, "email_verification_codes")
    if confirm:
        deleted = delete_expired_codes(db)
        print(f"  email_verification_codes: 清理了 {deleted} 条过期/已用验证码")
    else:
        print(f"  email_verification_codes: {count} 条（仅清理过期和已用的）")

    print("\n" + "-" * 60)
    if not confirm:
        print(f"总计: 业务数据 {total_business} 条, 用户数据 {total_users} 条")
        print("\n⚠️  使用 --confirm 参数执行实际删除操作")
    else:
        print("✓ 数据清理完成")
        print("\n下一步：")
        print("  1. 启动后端服务: ./run.sh")
        print("  2. 访问登录页面，注册第一个用户（自动成为管理员）")
    print("=" * 60)


def main():
    parser = ArgumentParser(description="CRMWolf 业务数据清理脚本")
    parser.add_argument("--confirm", action="store_true", help="确认执行删除操作")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        show_statistics(db, args.confirm)
    finally:
        db.close()


if __name__ == "__main__":
    main()