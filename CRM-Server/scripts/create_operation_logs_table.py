"""
创建操作记录表 (crm_operation_logs)

执行方式：
    PYTHONPATH=/Users/eddie/Code/CRM python scripts/create_operation_logs_table.py
"""

import sys
sys.path.insert(0, '/Users/eddie/Code/CRM')

from sqlalchemy import text
from app.core.database import get_db

def migrate():
    """创建操作记录表"""
    
    db = next(get_db())
    
    try:
        print("开始创建操作记录表...")
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS `crm_operation_logs` (
            `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
            `event_id` varchar(64) NOT NULL COMMENT '事件唯一ID',
            `event_type` varchar(50) NOT NULL COMMENT '事件类型',
            `event_action` varchar(20) NOT NULL COMMENT '事件动作',
            `primary_resource_type` varchar(20) NOT NULL COMMENT '主资源类型',
            `primary_resource_id` bigint NOT NULL COMMENT '主资源ID',
            `secondary_resource_type` varchar(20) DEFAULT NULL COMMENT '次资源类型',
            `secondary_resource_id` bigint DEFAULT NULL COMMENT '次资源ID',
            `operator_id` varchar(100) NOT NULL COMMENT '操作人ID',
            `operator_name` varchar(100) DEFAULT NULL COMMENT '操作人姓名',
            `operated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
            `content` json NOT NULL COMMENT '事件内容',
            `remark` varchar(500) DEFAULT NULL COMMENT '备注',
            PRIMARY KEY (`id`),
            UNIQUE KEY `idx_event_id` (`event_id`),
            KEY `idx_primary_resource` (`primary_resource_type`, `primary_resource_id`, `operated_at`),
            KEY `idx_event_type` (`event_type`),
            KEY `idx_operator_id` (`operator_id`),
            KEY `idx_operated_at` (`operated_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作记录表';
        """
        
        db.execute(text(create_table_sql))
        db.commit()
        
        print("✅ 操作记录表创建成功")
        
    except Exception as e:
        print(f"❌ 创建表失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
