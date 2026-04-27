"""
添加采购阶段管理相关字段的迁移脚本
包括：
1. 创建采购方式表 (crm_procurement_methods)
2. 创建采购阶段模板表 (crm_procurement_stage_templates)
3. 创建商机阶段快照表 (crm_opportunity_stage_snapshots)
4. 创建阶段模板变更日志表 (crm_stage_template_change_logs)
5. 客户表添加默认采购方式字段 (default_procurement_method_id)
6. 商机表添加采购方式相关字段
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from sqlalchemy import text


def upgrade():
    db = SessionLocal()
    try:
        print("开始迁移：添加采购阶段管理相关表和字段...")
        
        # 1. 创建采购方式表
        print("\n1. 创建采购方式表...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_procurement_methods (
                id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                code VARCHAR(50) NOT NULL UNIQUE COMMENT '采购方式编码，如: PUBLIC_BIDDING',
                name VARCHAR(100) NOT NULL COMMENT '采购方式名称，如：公开招标',
                description VARCHAR(500) NULL COMMENT '描述说明',
                is_active TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用: 1:启用, 0:停用',
                sort_order INT NOT NULL COMMENT '排序号，用于前端展示排序',
                created_by VARCHAR(100) NOT NULL COMMENT '创建人飞书用户ID',
                updated_by VARCHAR(100) NULL COMMENT '最后更新人飞书用户ID',
                created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
                INDEX ix_procurement_methods_sort_order (sort_order),
                INDEX ix_procurement_methods_is_active (is_active)
            ) COMMENT='采购方式表'
        """))
        print("✓ 采购方式表已创建")
        
        # 2. 创建采购阶段模板表
        print("\n2. 创建采购阶段模板表...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_procurement_stage_templates (
                id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                procurement_method_id BIGINT NOT NULL COMMENT '采购方式ID',
                template_code VARCHAR(50) NOT NULL COMMENT '模板阶段编码，同一方式下唯一',
                stage_name VARCHAR(100) NOT NULL COMMENT '阶段名称',
                win_probability INT NOT NULL COMMENT '阶段赢率 0-100',
                sort_order INT NOT NULL COMMENT '阶段顺序，同一方式下唯一，决定流程顺序',
                is_default_start TINYINT NOT NULL DEFAULT 0 COMMENT '默认起始阶段: 1:是, 0:否',
                can_skip TINYINT NOT NULL DEFAULT 0 COMMENT '是否可跳过: 1:是, 0:否',
                description VARCHAR(500) NULL COMMENT '阶段描述',
                version INT NOT NULL DEFAULT 1 COMMENT '版本号，从1开始，每次修改递增',
                version_lock INT NOT NULL DEFAULT 0 COMMENT '乐观锁版本，每次更新递增',
                created_by VARCHAR(100) NOT NULL COMMENT '创建人飞书用户ID',
                updated_by VARCHAR(100) NULL COMMENT '最后更新人飞书用户ID',
                created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
                FOREIGN KEY (procurement_method_id) REFERENCES crm_procurement_methods(id),
                UNIQUE INDEX ix_procurement_stage_templates_method_code (procurement_method_id, template_code),
                INDEX ix_procurement_stage_templates_sort_order (procurement_method_id, sort_order)
            ) COMMENT='采购阶段模板表'
        """))
        print("✓ 采购阶段模板表已创建")
        
        # 3. 创建商机阶段快照表
        print("\n3. 创建商机阶段快照表...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_opportunity_stage_snapshots (
                id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                opportunity_id BIGINT NOT NULL COMMENT '商机ID',
                procurement_stage_template_id BIGINT NOT NULL COMMENT '阶段模板ID',
                stage_name VARCHAR(100) NOT NULL COMMENT '快照：阶段名称，记录进入时的名称',
                win_probability INT NOT NULL COMMENT '快照：阶段赢率 0-100，记录进入时的赢率',
                template_sort_order INT NOT NULL COMMENT '快照：阶段顺序，记录进入时模板的sort_order',
                template_code VARCHAR(50) NOT NULL COMMENT '快照：阶段编码，记录进入时模板的编码',
                snapshot_version INT NOT NULL COMMENT '快照版本，对应模板版本',
                entered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '进入该阶段的时间',
                exited_at DATETIME NULL COMMENT '离开该阶段的时间，NULL表示当前阶段',
                INDEX ix_opportunity_stage_snapshots_opportunity_id (opportunity_id),
                INDEX ix_opportunity_stage_snapshots_entered_at (entered_at)
            ) COMMENT='商机阶段快照表'
        """))
        print("✓ 商机阶段快照表已创建")
        
        # 4. 创建阶段模板变更日志表
        print("\n4. 创建阶段模板变更日志表...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_stage_template_change_logs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                template_id BIGINT NOT NULL COMMENT '阶段模板ID',
                change_type VARCHAR(20) NOT NULL COMMENT '变更类型: CREATE, UPDATE, DELETE',
                old_data TEXT NULL COMMENT '变更前数据，旧值的JSON快照',
                new_data TEXT NULL COMMENT '变更后数据，新值的JSON快照',
                changed_by VARCHAR(100) NOT NULL COMMENT '变更人飞书用户ID',
                changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '变更时间',
                reason VARCHAR(500) NULL COMMENT '变更原因',
                INDEX ix_stage_template_change_logs_template_id (template_id),
                INDEX ix_stage_template_change_logs_changed_at (changed_at)
            ) COMMENT='阶段模板变更日志表'
        """))
        print("✓ 阶段模板变更日志表已创建")
        
        # 5. 客户表添加默认采购方式字段
        print("\n5. 客户表添加默认采购方式字段...")
        db.execute(text("""
            ALTER TABLE crm_customers 
            ADD COLUMN default_procurement_method_id BIGINT NULL COMMENT '客户默认采购方式ID' 
            AFTER source_lead_id
        """))
        print("✓ default_procurement_method_id 字段已添加到客户表")
        
        # 6. 商机表添加采购方式相关字段
        print("\n6. 商机表添加采购方式相关字段...")
        db.execute(text("""
            ALTER TABLE crm_opportunities 
            ADD COLUMN procurement_method_id BIGINT NULL COMMENT '商机实际采用的采购方式ID' 
            AFTER customer_id
        """))
        print("✓ procurement_method_id 字段已添加到商机表")
        
        db.execute(text("""
            ALTER TABLE crm_opportunities 
            ADD COLUMN current_stage_snapshot_id BIGINT NULL COMMENT '当前阶段快照ID' 
            AFTER procurement_method_id
        """))
        print("✓ current_stage_snapshot_id 字段已添加到商机表")
        
        db.execute(text("""
            ALTER TABLE crm_opportunities 
            ADD COLUMN current_stage_name VARCHAR(100) NULL COMMENT '当前阶段名称（冗余，用于快速查询）' 
            AFTER current_stage_snapshot_id
        """))
        print("✓ current_stage_name 字段已添加到商机表")
        
        db.execute(text("""
            ALTER TABLE crm_opportunities 
            ADD COLUMN current_win_probability INT NULL COMMENT '当前阶段赢率（冗余，用于快速查询）' 
            AFTER current_stage_name
        """))
        print("✓ current_win_probability 字段已添加到商机表")
        
        db.execute(text("""
            ALTER TABLE crm_opportunities 
            ADD COLUMN current_stage_entered_at DATETIME NULL COMMENT '当前阶段进入时间（冗余，用于时间范围查询）' 
            AFTER current_win_probability
        """))
        print("✓ current_stage_entered_at 字段已添加到商机表")
        
        db.commit()
        
        print("\n✅ 所有迁移完成！")
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def downgrade():
    db = SessionLocal()
    try:
        print("开始回滚：移除采购阶段管理相关表和字段...")
        
        # 回滚商机表字段
        print("\n1. 回滚商机表字段...")
        db.execute(text("ALTER TABLE crm_opportunities DROP COLUMN current_stage_entered_at"))
        print("✓ current_stage_entered_at 字段已删除")
        
        db.execute(text("ALTER TABLE crm_opportunities DROP COLUMN current_win_probability"))
        print("✓ current_win_probability 字段已删除")
        
        db.execute(text("ALTER TABLE crm_opportunities DROP COLUMN current_stage_name"))
        print("✓ current_stage_name 字段已删除")
        
        db.execute(text("ALTER TABLE crm_opportunities DROP COLUMN current_stage_snapshot_id"))
        print("✓ current_stage_snapshot_id 字段已删除")
        
        db.execute(text("ALTER TABLE crm_opportunities DROP COLUMN procurement_method_id"))
        print("✓ procurement_method_id 字段已删除")
        
        # 回滚客户表字段
        print("\n2. 回滚客户表字段...")
        db.execute(text("ALTER TABLE crm_customers DROP COLUMN default_procurement_method_id"))
        print("✓ default_procurement_method_id 字段已删除")
        
        # 删除日志表
        print("\n3. 删除阶段模板变更日志表...")
        db.execute(text("DROP TABLE IF EXISTS crm_stage_template_change_logs"))
        print("✓ 阶段模板变更日志表已删除")
        
        # 删除快照表
        print("\n4. 删除商机阶段快照表...")
        db.execute(text("DROP TABLE IF EXISTS crm_opportunity_stage_snapshots"))
        print("✓ 商机阶段快照表已删除")
        
        # 删除模板表
        print("\n5. 删除采购阶段模板表...")
        db.execute(text("DROP TABLE IF EXISTS crm_procurement_stage_templates"))
        print("✓ 采购阶段模板表已删除")
        
        # 删除采购方式表
        print("\n6. 删除采购方式表...")
        db.execute(text("DROP TABLE IF EXISTS crm_procurement_methods"))
        print("✓ 采购方式表已删除")
        
        db.commit()
        
        print("\n✅ 所有回滚完成！")
        
    except Exception as e:
        print(f"\n❌ 回滚失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
