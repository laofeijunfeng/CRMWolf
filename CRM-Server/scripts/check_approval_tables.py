#!/usr/bin/env python3
"""检查审批表是否存在"""

import sys
sys.path.append('/Users/eddie/Code/CRM')

from app.core.database import engine
from sqlalchemy import text

def check_tables():
    print("=" * 60)
    print("检查审批表")
    print("=" * 60)

    with engine.connect() as conn:
        # 查询所有表
        result = conn.execute(text("SHOW TABLES LIKE '%approval%'"))
        tables = result.fetchall()
        
        if tables:
            print(f"\n找到 {len(tables)} 个审批相关表：")
            for table in tables:
                table_name = table[0]
                print(f"\n{table_name}")
                
                # 查询表结构
                desc_result = conn.execute(text(f"DESCRIBE {table_name}"))
                columns = desc_result.fetchall()
                print(f"  列数: {len(columns)}")
                
                # 查询记录数
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = count_result.fetchone()[0]
                print(f"  记录数: {count}")
        else:
            print("\n未找到任何审批相关表")
            print("\n请运行以下脚本创建审批表：")
            print("  python scripts/migrate_approval_simple.py")

if __name__ == "__main__":
    check_tables()
