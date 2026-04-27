import logging
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(str(settings.DATABASE_URL))


def check_column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as count
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table_name}'
                AND COLUMN_NAME = '{column_name}'
            """))
            exists = result.fetchone()[0] > 0
            logger.info(f"列 {table_name}.{column_name} {'存在' if exists else '不存在'}")
            return exists
    except Exception as e:
        logger.error(f"检查列失败: {str(e)}")
        return False


def add_finance_fields_to_payment_records():
    """为 crm_payment_records 表添加财务确认相关字段"""
    
    table_name = "crm_payment_records"
    fields_to_add = [
        {
            "name": "confirmation_status",
            "definition": "VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '确认状态：PENDING(待确认), CONFIRMED(已确认), DISPUTED(有争议)'"
        },
        {
            "name": "confirmed_by",
            "definition": "VARCHAR(100) COMMENT '确认人（财务人员）飞书用户ID'"
        },
        {
            "name": "confirmed_by_name",
            "definition": "VARCHAR(100) COMMENT '确认人姓名'"
        },
        {
            "name": "confirmed_time",
            "definition": "DATETIME COMMENT '确认入账时间'"
        },
        {
            "name": "confirmation_notes",
            "definition": "TEXT COMMENT '确认备注'"
        }
    ]
    
    logger.info(f"开始为表 {table_name} 添加财务确认字段...")
    
    for field in fields_to_add:
        column_name = field["name"]
        column_definition = field["definition"]
        
        if check_column_exists(table_name, column_name):
            logger.info(f"✅ 字段 {column_name} 已存在，跳过添加")
            continue
        
        try:
            with engine.connect() as conn:
                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                logger.info(f"执行SQL: {alter_sql}")
                conn.execute(text(alter_sql))
                conn.commit()
                logger.info(f"✅ 成功添加字段 {column_name}")
        except Exception as e:
            logger.error(f"❌ 添加字段 {column_name} 失败: {str(e)}")
            return False
    
    logger.info(f"✅ 表 {table_name} 财务确认字段添加完成")
    return True


def verify_migration():
    """验证迁移结果"""
    logger.info("\n" + "="*80)
    logger.info("验证迁移结果")
    logger.info("="*80)
    
    table_name = "crm_payment_records"
    required_columns = [
        "confirmation_status",
        "confirmed_by",
        "confirmed_by_name",
        "confirmed_time",
        "confirmation_notes"
    ]
    
    all_exist = True
    for column in required_columns:
        exists = check_column_exists(table_name, column)
        if exists:
            logger.info(f"✅ 字段 {column} 存在")
        else:
            logger.error(f"❌ 字段 {column} 不存在")
            all_exist = False
    
    if all_exist:
        logger.info("✅ 所有字段验证通过")
    else:
        logger.error("❌ 字段验证失败")
    
    return all_exist


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 财务功能字段迁移")
    logger.info("="*80)
    
    success = add_finance_fields_to_payment_records()
    
    if success:
        verify_migration()
        logger.info("\n" + "="*80)
        logger.info("✅ 迁移完成！")
        logger.info("="*80)
    else:
        logger.error("\n" + "="*80)
        logger.error("❌ 迁移失败！")
        logger.error("="*80)


if __name__ == "__main__":
    main()
