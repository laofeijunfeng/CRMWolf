from app.core.database import engine
from sqlalchemy import text

def migrate_contacts_final():
    with engine.connect() as conn:
        with conn.begin():
            print("开始更新联系人表...")
            
            conn.execute(text("ALTER TABLE crm_contacts DROP FOREIGN KEY crm_contacts_ibfk_1"))
            print("已删除外键 crm_contacts_ibfk_1")
            
            conn.execute(text("DROP INDEX idx_account_id ON crm_contacts"))
            print("已删除旧索引 idx_account_id")
            
            conn.execute(text("ALTER TABLE crm_contacts CHANGE account_id customer_id BIGINT NOT NULL COMMENT '所属客户ID'"))
            print("已将 account_id 列重命名为 customer_id")
            
            conn.execute(text("CREATE INDEX idx_customer_id ON crm_contacts(customer_id)"))
            print("已创建新索引 idx_customer_id")
            
            conn.execute(text("""
                ALTER TABLE crm_contacts 
                ADD CONSTRAINT fk_crm_contacts_customer_id 
                FOREIGN KEY (customer_id) REFERENCES crm_customers(id) ON DELETE CASCADE
            """))
            print("已添加新外键 fk_crm_contacts_customer_id")
            
            conn.execute(text("ALTER TABLE crm_customer_follow_ups DROP FOREIGN KEY crm_customer_follow_ups_ibfk_1"))
            print("已删除外键 crm_customer_follow_ups_ibfk_1")
            
            conn.execute(text("""
                ALTER TABLE crm_customer_follow_ups 
                ADD CONSTRAINT fk_crm_customer_follow_ups_customer_id 
                FOREIGN KEY (customer_id) REFERENCES crm_customers(id) ON DELETE CASCADE
            """))
            print("已添加新外键 fk_crm_customer_follow_ups_customer_id")
            
            print("数据库迁移完成！")

if __name__ == "__main__":
    try:
        migrate_contacts_final()
        print("迁移成功！")
    except Exception as e:
        print(f"迁移失败: {e}")
        raise
