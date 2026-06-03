"""
为跟进记录表添加 next_action 字段

执行方式：
cd CRM-Server && python scripts/add_next_action_field.py
"""

import sys
sys.path.insert(0, '/Users/eddie/Code/CRMWolf/CRM-Server')

from sqlalchemy import text
from app.core.database import SessionLocal, engine


def migrate():
    db = SessionLocal()

    try:
        # 检查字段是否已存在
        result = db.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'crm_db'
            AND TABLE_NAME = 'crm_lead_follow_ups'
            AND COLUMN_NAME = 'next_action'
        """))

        if result.fetchone():
            print("lead_follow_ups 表已存在 next_action 字段")
        else:
            # 添加 lead_follow_ups 表的 next_action 字段
            db.execute(text("""
                ALTER TABLE crm_lead_follow_ups
                ADD COLUMN next_action TEXT NULL COMMENT '下一步动作内容'
                AFTER next_follow_time
            """))
            print("已为 crm_lead_follow_ups 表添加 next_action 字段")

        # 检查 customer_follow_ups 表
        result = db.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'crm_db'
            AND TABLE_NAME = 'crm_customer_follow_ups'
            AND COLUMN_NAME = 'next_action'
        """))

        if result.fetchone():
            print("customer_follow_ups 表已存在 next_action 字段")
        else:
            # 添加 customer_follow_ups 表的 next_action 字段
            db.execute(text("""
                ALTER TABLE crm_customer_follow_ups
                ADD COLUMN next_action TEXT NULL COMMENT '下一步动作内容'
                AFTER next_follow_time
            """))
            print("已为 crm_customer_follow_ups 表添加 next_action 字段")

        db.commit()
        print("迁移完成！")

    except Exception as e:
        db.rollback()
        print(f"迁移失败: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()