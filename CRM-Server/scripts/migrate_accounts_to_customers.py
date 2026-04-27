from app.core.database import engine
from sqlalchemy import text

def migrate_accounts_to_customers():
    with engine.connect() as conn:
        with conn.begin():
            print("开始迁移数据库表...")
            
            conn.execute(text("RENAME TABLE crm_accounts TO crm_customers"))
            print("表 crm_accounts 已重命名为 crm_customers")
            
            conn.execute(text("""
                ALTER TABLE crm_contacts 
                DROP FOREIGN KEY fk_crm_contacts_account_id
            """))
            print("已删除联系人表旧外键")
            
            conn.execute(text("""
                ALTER TABLE crm_contacts 
                ADD CONSTRAINT fk_crm_contacts_customer_id 
                FOREIGN KEY (customer_id) REFERENCES crm_customers(id) ON DELETE CASCADE
            """))
            print("已添加联系人表新外键")
            
            conn.execute(text("DROP INDEX idx_account_id ON crm_contacts"))
            print("已删除旧索引 idx_account_id")
            
            conn.execute(text("CREATE INDEX idx_customer_id ON crm_contacts(customer_id)"))
            print("已创建新索引 idx_customer_id")
            
            conn.execute(text("""
                ALTER TABLE crm_customer_follow_ups 
                DROP FOREIGN KEY fk_crm_customer_follow_ups_customer_id
            """))
            print("已删除客户跟进表旧外键")
            
            conn.execute(text("""
                ALTER TABLE crm_customer_follow_ups 
                ADD CONSTRAINT fk_crm_customer_follow_ups_customer_id 
                FOREIGN KEY (customer_id) REFERENCES crm_customers(id) ON DELETE CASCADE
            """))
            print("已添加客户跟进表新外键")
            
            print("数据库迁移完成！")

if __name__ == "__main__":
    try:
        migrate_accounts_to_customers()
        print("迁移成功！")
    except Exception as e:
        print(f"迁移失败: {e}")
        raise
