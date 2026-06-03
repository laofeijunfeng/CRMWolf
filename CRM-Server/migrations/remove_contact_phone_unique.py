"""
移除 crm_leads 表 contact_phone 字段的唯一约束

业务场景：客户删除后再次回来，可能使用相同手机号
"""
from sqlalchemy import text
from app.core.database import engine


def remove_contact_phone_unique_constraint():
    """移除手机号唯一约束"""
    print("开始移除 contact_phone 唯一约束...")

    with engine.connect() as conn:
        # 查看当前索引
        result = conn.execute(text("SHOW INDEX FROM crm_leads WHERE Column_name = 'contact_phone'"))
        indexes = result.fetchall()

        for idx in indexes:
            idx_name = idx[2]  # Key_name
            if idx_name == 'contact_phone':  # unique constraint 的索引名通常就是字段名
                print(f"删除索引: {idx_name}")
                conn.execute(text(f"ALTER TABLE crm_leads DROP INDEX `{idx_name}`"))
                conn.commit()
                print("唯一约束已移除")
                return

        print("未找到 contact_phone 唯一索引，可能已移除")


if __name__ == "__main__":
    remove_contact_phone_unique_constraint()