"""
客户表添加退回公海相关字段的迁移脚本
"""
from app.core.database import SessionLocal
from sqlalchemy import text


def upgrade():
    db = SessionLocal()
    try:
        print("开始迁移：添加客户退回公海字段...")
        
        db.execute(text("""
            ALTER TABLE crm_customers 
            MODIFY COLUMN owner_id VARCHAR(100) NULL COMMENT '负责人（飞书用户ID）'
        """))
        print("✓ owner_id 字段已修改为可空")
        
        db.execute(text("""
            ALTER TABLE crm_customers 
            ADD COLUMN return_reason VARCHAR(255) NULL COMMENT '退回公海原因' 
            AFTER source_lead_id
        """))
        print("✓ return_reason 字段已添加")
        
        db.execute(text("""
            ALTER TABLE crm_customers 
            ADD COLUMN returned_time DATETIME NULL COMMENT '退回公海时间' 
            AFTER return_reason
        """))
        print("✓ returned_time 字段已添加")
        
        db.commit()
        
        print("迁移完成！")
        
    except Exception as e:
        print(f"迁移失败: {e}")
        db.rollback()
    finally:
        db.close()


def downgrade():
    db = SessionLocal()
    try:
        print("开始回滚：移除客户退回公海字段...")
        
        db.execute(text("""
            ALTER TABLE crm_customers 
            DROP COLUMN returned_time
        """))
        print("✓ returned_time 字段已删除")
        
        db.execute(text("""
            ALTER TABLE crm_customers 
            DROP COLUMN return_reason
        """))
        print("✓ return_reason 字段已删除")
        
        db.execute(text("""
            ALTER TABLE crm_customers 
            MODIFY COLUMN owner_id VARCHAR(100) NOT NULL COMMENT '负责人（飞书用户ID）'
        """))
        print("✓ owner_id 字段已恢复为必填")
        
        db.commit()
        
        print("回滚完成！")
        
    except Exception as e:
        print(f"回滚失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
