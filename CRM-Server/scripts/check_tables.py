"""
检查数据库中的实际表名
"""
from app.core.database import SessionLocal
from sqlalchemy import text


def check_tables():
    db = SessionLocal()
    try:
        result = db.execute(text("SHOW TABLES")).fetchall()
        print("数据库中的所有表:")
        for (table_name,) in result:
            print(f"  - {table_name}")
    finally:
        db.close()


if __name__ == "__main__":
    check_tables()
