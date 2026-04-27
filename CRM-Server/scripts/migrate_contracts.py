from app.core.database import get_db
from sqlalchemy import text

db = next(get_db())

with open('migrate_create_contracts_table.sql', 'r', encoding='utf-8') as f:
    sql_script = f.read()

try:
    result = db.execute(text(sql_script))
    db.commit()
    print('✅ 合同表创建成功！')
    
    tables = db.execute(text('SHOW TABLES LIKE "crm_contracts"'))
    if tables.first():
        print('✅ 验证：crm_contracts 表已存在')
        
        desc = db.execute(text('DESCRIBE crm_contracts'))
        print('\n表结构：')
        for row in desc:
            print(f"  {row[0]:<25} {row[1]:<20} {row[2]}")
    else:
        print('❌ 验证失败：crm_contracts 表未找到')
except Exception as e:
    print(f'❌ 创建合同表失败: {str(e)}')
finally:
    db.close()
