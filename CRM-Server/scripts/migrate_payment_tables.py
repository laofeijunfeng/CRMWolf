#!/usr/bin/env python3
"""创建回款管理相关表"""

import sys
sys.path.append('/Users/eddie/Code/CRM')

from app.core.database import engine
from sqlalchemy import text

def migrate_payment_tables():
    print("=" * 60)
    print("开始创建回款管理表")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            # 创建回款计划表
            print("\n1. 创建回款计划表...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS `crm_contract_payment_plans` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                  `contract_id` BIGINT NOT NULL COMMENT '关联的合同ID',
                  `stage_name` VARCHAR(100) NOT NULL COMMENT '回款阶段名，如：首付款、中期款、尾款',
                  `planned_amount` DECIMAL(12, 2) NOT NULL COMMENT '计划回款金额',
                  `due_date` DATE NOT NULL COMMENT '计划回款日期',
                  `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '回款状态：PENDING, OVERDUE, PARTIAL, COMPLETED',
                  `notes` TEXT COMMENT '备注',
                  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                  `last_modified_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后修改时间',
                  PRIMARY KEY (`id`),
                  KEY `idx_plan_contract` (`contract_id`),
                  KEY `idx_plan_status` (`status`),
                  KEY `idx_plan_due_date` (`due_date`),
                  CONSTRAINT `fk_plan_contract` FOREIGN KEY (`contract_id`) REFERENCES `crm_contracts` (`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='合同回款计划表';
            """))
            print("✅ 回款计划表创建完成")
            
            # 创建回款记录表
            print("\n2. 创建回款记录表...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS `crm_payment_records` (
                  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                  `payment_plan_id` BIGINT NOT NULL COMMENT '关联的回款计划ID',
                  `actual_amount` DECIMAL(12, 2) NOT NULL COMMENT '实际回款金额',
                  `payment_date` DATE NOT NULL COMMENT '实际回款日期',
                  `proof_attachment` VARCHAR(500) COMMENT '回款凭证附件URL',
                  `notes` TEXT COMMENT '备注',
                  `creator_id` VARCHAR(100) NOT NULL COMMENT '创建人（登记人）飞书用户ID',
                  `creator_name` VARCHAR(100) COMMENT '创建人姓名',
                  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                  PRIMARY KEY (`id`),
                  KEY `idx_record_plan` (`payment_plan_id`),
                  KEY `idx_record_date` (`payment_date`),
                  CONSTRAINT `fk_record_plan` FOREIGN KEY (`payment_plan_id`) REFERENCES `crm_contract_payment_plans` (`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回款记录表';
            """))
            print("✅ 回款记录表创建完成")
            
            # 为合同表添加回款相关字段
            print("\n3. 为合同表添加回款相关字段...")
            
            # 检查字段是否已存在
            result = conn.execute(text("SHOW COLUMNS FROM crm_contracts LIKE 'total_paid_amount'"))
            if not result.fetchone():
                conn.execute(text("""
                    ALTER TABLE `crm_contracts`
                    ADD COLUMN `total_paid_amount` DECIMAL(12, 2) NOT NULL DEFAULT 0 COMMENT '累计已回款金额' AFTER `expiry_date`,
                    ADD COLUMN `payment_status` VARCHAR(20) NOT NULL DEFAULT 'UNPAID' COMMENT '合同回款状态：UNPAID, PARTIAL, COMPLETED, OVERDUE' AFTER `total_paid_amount`,
                    ADD INDEX `idx_contract_payment_status` (`payment_status`);
                """))
                print("✅ 合同表字段添加完成")
            else:
                print("ℹ️  合同表字段已存在，跳过")
            
            # 提交事务
            conn.commit()
            
            print("\n" + "=" * 60)
            print("✅ 回款管理表创建完成！")
            print("=" * 60)
            
    except Exception as e:
        print(f"\n❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    migrate_payment_tables()
