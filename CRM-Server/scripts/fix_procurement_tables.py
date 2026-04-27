import logging
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    logger.error("环境变量DATABASE_URL未设置")
    sys.exit(1)

engine = create_engine(DATABASE_URL)


def check_table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                AND table_name = '{table_name}'
            """))
            return result.fetchone()[0] > 0
    except Exception as e:
        logger.error(f"检查表失败: {e}")
        return False


def get_table_columns(table_name: str) -> list:
    """获取表的列信息"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"DESCRIBE {table_name}"))
            columns = [row[0] for row in result]
            return columns
    except Exception as e:
        logger.error(f"获取表结构失败: {e}")
        return []


def add_column_if_not_exists(table_name: str, column_name: str, column_definition: str):
    """添加列（如果不存在）"""
    if not check_table_exists(table_name):
        logger.warning(f"⚠️  表 {table_name} 不存在，跳过")
        return False
    
    current_columns = get_table_columns(table_name)
    if column_name in current_columns:
        logger.info(f"  ✅ {table_name}.{column_name} 已存在")
        return True
    
    try:
        with engine.connect() as conn:
            sql = text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
            conn.execute(sql)
            conn.commit()
            logger.info(f"  ✅ 成功添加列: {table_name}.{column_name}")
            return True
    except Exception as e:
        logger.error(f"  ❌ 添加列失败 {table_name}.{column_name}: {e}")
        return False


def fix_procurement_tables():
    """修复采购管理相关表结构"""
    
    # 修复 crm_procurement_methods 表
    logger.info("\n修复 crm_procurement_methods 表:")
    add_column_if_not_exists(
        'crm_procurement_methods',
        'created_by',
        "VARCHAR(100) COMMENT '创建人飞书用户ID'"
    )
    add_column_if_not_exists(
        'crm_procurement_methods',
        'updated_by',
        "VARCHAR(100) COMMENT '最后更新人飞书用户ID'"
    )
    add_column_if_not_exists(
        'crm_procurement_methods',
        'created_time',
        "DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'"
    )
    add_column_if_not_exists(
        'crm_procurement_methods',
        'updated_time',
        "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间'"
    )
    
    # 修复 crm_procurement_stage_templates 表
    logger.info("\n修复 crm_procurement_stage_templates 表:")
    add_column_if_not_exists(
        'crm_procurement_stage_templates',
        'created_by',
        "VARCHAR(100) COMMENT '创建人飞书用户ID'"
    )
    add_column_if_not_exists(
        'crm_procurement_stage_templates',
        'updated_by',
        "VARCHAR(100) COMMENT '最后更新人飞书用户ID'"
    )
    add_column_if_not_exists(
        'crm_procurement_stage_templates',
        'created_time',
        "DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'"
    )
    add_column_if_not_exists(
        'crm_procurement_stage_templates',
        'updated_time',
        "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间'"
    )


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 修复采购管理表结构")
    logger.info("="*80)
    
    fix_procurement_tables()
    
    logger.info("\n" + "="*80)
    logger.info("✅ 表结构修复完成！")
    logger.info("="*80)


if __name__ == "__main__":
    main()
