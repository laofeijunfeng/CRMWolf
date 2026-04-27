from app.core.database import engine
from sqlalchemy import text

def migrate_contacts_column():
    with engine.connect() as conn:
        with conn.begin():
            print("开始更新联系人表...")
            
            conn.execute(text("DROP INDEX idx_account_id ON crm_contacts"))
            print("已删除旧索引 idx_account_id")
            
            conn.execute(text("ALTER TABLE crm_contacts CHANGE account_id customer_id BIGINT NOT NULL COMMENT '所属客户ID'"))
            print("已将 account_id 列重命名为 customer_id")
            
            conn.execute(text("CREATE INDEX idx_customer_id ON crm_contacts(customer_id)"))
            print("已创建新索引 idx_customer_id")
            
            print("联系人表更新完成！")

if __name__ == "__main__":
    try:
        migrate_contacts_column()
        print("迁移成功！")
    except Exception as e:
        print(f"迁移失败: {e}")
        raise
