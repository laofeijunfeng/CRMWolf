"""
发票管理模块 - 数据库迁移脚本
创建开票抬头表和发票申请表
"""

from app.core.database import engine
from sqlalchemy import text, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_table_exists(table_name):
    """检查表是否存在"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def create_invoice_titles_table():
    """创建开票抬头表"""
    if check_table_exists('crm_invoice_titles'):
        logger.info("✅ 表 crm_invoice_titles 已存在，跳过创建")
        return True
    
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE crm_invoice_titles (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                    customer_id BIGINT NOT NULL COMMENT '关联客户ID',
                    title_type VARCHAR(10) NOT NULL COMMENT '抬头类型：COMPANY(单位), PERSONAL(个人)',
                    title VARCHAR(255) NOT NULL COMMENT '开票抬头',
                    taxpayer_id VARCHAR(100) NOT NULL COMMENT '纳税人识别号',
                    bank_name VARCHAR(255) COMMENT '开户行',
                    bank_account VARCHAR(100) COMMENT '开户账号',
                    address VARCHAR(500) COMMENT '开票地址',
                    phone VARCHAR(50) COMMENT '电话',
                    is_default TINYINT NOT NULL DEFAULT 0 COMMENT '是否默认抬头：0:否, 1:是',
                    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    last_modified_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后修改时间',
                    FOREIGN KEY (customer_id) REFERENCES crm_customers(id) ON DELETE CASCADE,
                    INDEX idx_customer_id (customer_id),
                    INDEX idx_taxpayer_id (taxpayer_id)
                ) COMMENT='开票抬头表'
            """))
            conn.commit()
            logger.info("✅ 成功创建表 crm_invoice_titles")
            return True
    except Exception as e:
        logger.error(f"❌ 创建表 crm_invoice_titles 失败: {str(e)}")
        return False


def create_invoice_applications_table():
    """创建发票申请表"""
    if check_table_exists('crm_invoice_applications'):
        logger.info("✅ 表 crm_invoice_applications 已存在，跳过创建")
        return True
    
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE crm_invoice_applications (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
                    application_number VARCHAR(50) NOT NULL UNIQUE COMMENT '申请单号',
                    customer_id BIGINT NOT NULL COMMENT '关联客户ID',
                    contract_id BIGINT NOT NULL COMMENT '关联合同ID',
                    opportunity_id BIGINT NOT NULL COMMENT '关联商机ID',
                    payment_plan_id BIGINT NOT NULL COMMENT '关联回款计划ID',
                    payment_record_id BIGINT COMMENT '关联回款记录ID',
                    invoice_title_id BIGINT NOT NULL COMMENT '开票抬头ID',
                    invoice_amount DECIMAL(12, 2) NOT NULL COMMENT '开票金额',
                    invoice_type VARCHAR(20) NOT NULL COMMENT '发票类型：VAT_SPECIAL(增值税专用发票), VAT_NORMAL(普通发票)',
                    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' COMMENT '申请状态：DRAFT, PENDING_REVIEW, APPROVED, REJECTED, ISSUED',
                    applicant_id VARCHAR(100) NOT NULL COMMENT '申请人ID（飞书用户ID）',
                    reviewer_id VARCHAR(100) COMMENT '审批人ID（飞书用户ID）',
                    review_comment VARCHAR(500) COMMENT '审批意见',
                    reviewed_time DATETIME COMMENT '审批时间',
                    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    last_modified_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后修改时间',
                    FOREIGN KEY (customer_id) REFERENCES crm_customers(id) ON DELETE CASCADE,
                    FOREIGN KEY (contract_id) REFERENCES crm_contracts(id) ON DELETE CASCADE,
                    FOREIGN KEY (opportunity_id) REFERENCES crm_opportunities(id) ON DELETE CASCADE,
                    FOREIGN KEY (payment_plan_id) REFERENCES crm_contract_payment_plans(id) ON DELETE CASCADE,
                    FOREIGN KEY (payment_record_id) REFERENCES crm_payment_records(id) ON DELETE SET NULL,
                    FOREIGN KEY (invoice_title_id) REFERENCES crm_invoice_titles(id) ON DELETE CASCADE,
                    INDEX idx_application_number (application_number),
                    INDEX idx_customer_id (customer_id),
                    INDEX idx_contract_id (contract_id),
                    INDEX idx_payment_plan_id (payment_plan_id),
                    INDEX idx_status (status),
                    INDEX idx_applicant_id (applicant_id),
                    INDEX idx_created_time (created_time)
                ) COMMENT='发票申请表'
            """))
            conn.commit()
            logger.info("✅ 成功创建表 crm_invoice_applications")
            return True
    except Exception as e:
        logger.error(f"❌ 创建表 crm_invoice_applications 失败: {str(e)}")
        return False


def run_migration():
    """执行数据库迁移"""
    logger.info("=" * 60)
    logger.info("开始执行发票管理模块数据库迁移")
    logger.info("=" * 60)
    
    # 创建开票抬头表
    logger.info("\n1. 创建开票抬头表...")
    success1 = create_invoice_titles_table()
    
    # 创建发票申请表
    logger.info("\n2. 创建发票申请表...")
    success2 = create_invoice_applications_table()
    
    logger.info("\n" + "=" * 60)
    if success1 and success2:
        logger.info("✅ 发票管理模块数据库迁移完成！")
    else:
        logger.error("❌ 发票管理模块数据库迁移未完全成功，请检查错误信息")
    logger.info("=" * 60)
    
    return success1 and success2


if __name__ == "__main__":
    run_migration()
