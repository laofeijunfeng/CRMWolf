"""
检查现有权限的映射关系
"""
import logging
from sqlalchemy import create_engine, text
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_engine(settings.get_database_url())


def check_permission_mapping():
    """检查权限的映射关系"""
    logger.info("="*80)
    logger.info("检查现有权限映射关系")
    logger.info("="*80)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT code, name, resource, action, scope
                FROM permissions
                WHERE code LIKE '%view%' OR code LIKE '%follow_up%'
                ORDER BY resource, action
            """))
            
            logger.info("\n现有查看和跟进相关权限:")
            for row in result:
                scope_info = f" (scope: {row[4]})" if row[4] else ""
                log_msg = f"  - {row[0]}: {row[1]} [{row[2]}.{row[3]}{scope_info}]"
                logger.info(log_msg)
    except Exception as e:
        logger.error(f"❌ 检查权限映射失败: {str(e)}")


def find_missing_permission_codes():
    """查找缺失的权限代码"""
    logger.info("\n" + "="*80)
    logger.info("查找缺失的权限代码")
    logger.info("="*80)
    
    needed_permissions = [
        "lead_follow_up:create",
        "opportunity:view_own",
        "customer:view_own",
        "customer_contact:create",
        "customer_contact:edit",
        "customer_follow_up:create",
        "customer_follow_up:edit",
        "payment_plan:view_all",
        "finance:view_receivables",
        "finance:view_reports",
        "report:view",
        "opportunity:view_all",
        "customer:view_all"
    ]
    
    try:
        with engine.connect() as conn:
            for code in needed_permissions:
                result = conn.execute(text(f"""
                    SELECT code, name FROM permissions WHERE code = '{code}'
                """))
                row = result.fetchone()
                if row:
                    logger.info(f"✅ {code}: {row[1]}")
                else:
                    logger.warning(f"❌ {code}: 不存在")
    except Exception as e:
        logger.error(f"❌ 查找缺失权限代码失败: {str(e)}")


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 权限映射检查")
    logger.info("="*80)
    
    check_permission_mapping()
    find_missing_permission_codes()
    
    logger.info("\n" + "="*80)
    logger.info("✅ 检查完成！")
    logger.info("="*80)


if __name__ == "__main__":
    main()
