#!/usr/bin/env python3
"""
邮箱认证系统数据库迁移脚本

用途：
1. 确保 email_verification_codes 表存在
2. 确保 users 表有 password_hash 字段
3. 确保 users.email 字段不为空

使用方式：
    python scripts/migrate_email_auth.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine, SessionLocal, Base


def check_table_exists(db, table_name: str) -> bool:
    """检查表是否存在"""
    result = db.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = :table_name
    """), {"table_name": table_name})
    return result.scalar() > 0


def check_column_exists(db, table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    result = db.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = :table_name
        AND column_name = :column_name
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar() > 0


def create_email_verification_codes_table(db):
    """创建验证码表"""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS email_verification_codes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) NOT NULL COMMENT '邮箱地址',
            code VARCHAR(6) NOT NULL COMMENT '6位验证码',
            purpose ENUM('REGISTER', 'LOGIN', 'RESET_PASSWORD') NOT NULL COMMENT '验证码用途',
            expires_at DATETIME NOT NULL COMMENT '过期时间',
            used BOOLEAN DEFAULT FALSE COMMENT '是否已使用',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            INDEX idx_email (email)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    db.commit()
    print("✓ 创建 email_verification_codes 表")


def add_password_hash_column(db):
    """添加 password_hash 列"""
    if check_column_exists(db, "users", "password_hash"):
        print("✓ users.password_hash 列已存在")
        return

    db.execute(text("""
        ALTER TABLE users
        ADD COLUMN password_hash VARCHAR(255) NULL COMMENT '密码哈希（可选）'
    """))
    db.commit()
    print("✓ 添加 users.password_hash 列")


def migrate_email_column(db):
    """确保 email 列不为空"""
    result = db.execute(text("""
        SELECT column_name, is_nullable, column_type
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'users'
        AND column_name = 'email'
    """))
    row = result.first()

    if row and row[1] == 'NO':
        print("✓ users.email 已设置为 NOT NULL")
        return

    # 先将空值更新为默认值
    db.execute(text("""
        UPDATE users SET email = CONCAT('user_', id, '@temp.local')
        WHERE email IS NULL OR email = ''
    """))
    db.commit()

    # 然后修改列
    db.execute(text("""
        ALTER TABLE users
        MODIFY COLUMN email VARCHAR(255) NOT NULL COMMENT '邮箱（主登录标识）'
    """))
    db.commit()
    print("✓ 设置 users.email 为 NOT NULL")


def make_feishu_columns_nullable(db):
    """将飞书相关字段设置为 nullable"""
    feishu_columns = [
        "feishu_open_id",
        "feishu_union_id",
        "feishu_user_id",
        "tenant_key",
        "en_name"
    ]

    for column in feishu_columns:
        db.execute(text(f"""
            ALTER TABLE users
            MODIFY COLUMN {column} VARCHAR(100) NULL
        """))
    db.commit()
    print(f"✓ 设置飞书相关字段为 nullable: {', '.join(feishu_columns)}")


def main():
    print("\n" + "=" * 60)
    print("CRMWolf 邮箱认证系统数据库迁移")
    print("=" * 60 + "\n")

    # 使用 SQLAlchemy 创建所有表（包括新模型）
    print("步骤 1: 同步数据库表结构...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("\n步骤 2: 检查并创建验证码表...")
        if check_table_exists(db, "email_verification_codes"):
            print("✓ email_verification_codes 表已存在")
        else:
            create_email_verification_codes_table(db)

        print("\n步骤 3: 检查 users 表字段...")
        if check_table_exists(db, "users"):
            add_password_hash_column(db)
            migrate_email_column(db)
            make_feishu_columns_nullable(db)
        else:
            print("⚠️  users 表不存在，请先运行 init_db.py")

        print("\n" + "=" * 60)
        print("✓ 迁移完成")
        print("\n下一步：")
        print("  1. 运行数据清理: python scripts/cleanup_business_data.py --confirm")
        print("  2. 启动后端服务: ./run.sh")
        print("  3. 注册第一个用户（自动成为管理员）")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    main()