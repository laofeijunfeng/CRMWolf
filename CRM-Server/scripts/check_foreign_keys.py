from app.core.database import engine
from sqlalchemy import text

def check_foreign_keys():
    with engine.connect() as conn:
        result = conn.execute(text("SHOW CREATE TABLE crm_contacts"))
        print("crm_contacts 表结构:")
        for row in result:
            print(row[1])
        
        result = conn.execute(text("SHOW CREATE TABLE crm_customer_follow_ups"))
        print("\ncrm_customer_follow_ups 表结构:")
        for row in result:
            print(row[1])

if __name__ == "__main__":
    check_foreign_keys()
