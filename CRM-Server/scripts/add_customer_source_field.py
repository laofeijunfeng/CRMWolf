"""
为客户表添加来源字段 (source)

执行方式：
    PYTHONPATH=/Users/eddie/Code/CRM python scripts/add_customer_source_field.py
"""

import sys
sys.path.insert(0, '/Users/eddie/Code/CRM')

from sqlalchemy import text
from app.core.database import get_db

def migrate():
    """为客户表添加 source 字段"""
    
    db = next(get_db())
    
    try:
        print("开始为客户表添加 source 字段...")
        
        # 检查字段是否已存在
        check_sql = """
            SELECT COUNT(*) as count 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'crm_customers' 
            AND COLUMN_NAME = 'source'
        """
        
        result = db.execute(text(check_sql)).fetchone()
        
        if result[0] > 0:
            print("⚠️  source 字段已存在，跳过添加")
        else:
            # 添加 source 字段
            add_column_sql = """
                ALTER TABLE crm_customers 
                ADD COLUMN source ENUM(
                    '线上注册',
                    '市场活动',
                    '客户推荐',
                    '电话营销',
                    '网站咨询',
                    '展会',
                    '其他',
                    '线索转化'
                ) NULL COMMENT '客户来源' 
                AFTER company_scale
            """
            
            db.execute(text(add_column_sql))
            print("✅ 成功添加 source 字段")
            
            # 如果客户有来源线索，更新 source 字段为"线索转化"
            update_sql = """
                UPDATE crm_customers 
                SET source = '线索转化' 
                WHERE source_lead_id IS NOT NULL 
                AND source IS NULL
            """
            
            result = db.execute(text(update_sql))
            db.commit()
            
            print(f"✅ 已将 {result.rowcount} 个从线索转化的客户的来源更新为'线索转化'")
        
        print("\n迁移完成！")
        
    except Exception as e:
        print(f"❌ 迁移失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
