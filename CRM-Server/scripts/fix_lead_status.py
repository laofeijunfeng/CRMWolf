"""
修复线索状态数据
将所有有负责人但状态为"新建"的线索更新为"跟进中"
"""
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.get_database_url())

def fix_lead_status():
    """修复有负责人但状态为新建的线索"""
    with engine.connect() as conn:
        # 查询需要修复的数据
        result = conn.execute(text("""
            SELECT id, lead_name, owner_id, status 
            FROM leads 
            WHERE owner_id IS NOT NULL AND status = 0
        """))
        
        leads_to_fix = result.fetchall()
        
        if not leads_to_fix:
            print("没有需要修复的数据")
            return
        
        print(f"发现 {len(leads_to_fix)} 条需要修复的线索:")
        for lead in leads_to_fix:
            print(f"  ID={lead[0]}, 名称={lead[1]}, 负责人={lead[2]}, 当前状态={lead[3]}")
        
        # 执行修复
        conn.execute(text("""
            UPDATE leads 
            SET status = 1, version = version + 1
            WHERE owner_id IS NOT NULL AND status = 0
        """))
        conn.commit()
        
        print(f"✅ 已修复 {len(leads_to_fix)} 条线索状态")

if __name__ == "__main__":
    fix_lead_status()
