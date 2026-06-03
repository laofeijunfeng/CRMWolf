"""
创建缺失的权限
"""
import logging
from sqlalchemy import create_engine, text
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_engine(settings.get_database_url())


def check_permission_exists(code: str) -> bool:
    """检查权限是否存在"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as count
                FROM permissions
                WHERE code = '{code}'
            """))
            exists = result.fetchone()[0] > 0
            return exists
    except Exception as e:
        logger.error(f"检查权限失败: {str(e)}")
        return False


def create_permission(code: str, name: str, resource: str, action: str, description: str, scope: str = None):
    """创建权限"""
    if check_permission_exists(code):
        logger.info(f"✅ 权限 {code} 已存在，跳过创建")
        return
    
    try:
        with engine.connect() as conn:
            insert_sql = text("""
                INSERT INTO permissions (code, name, resource, action, description, scope, created_at, updated_at)
                VALUES (:code, :name, :resource, :action, :description, :scope, NOW(), NOW())
            """)
            conn.execute(insert_sql, {
                "code": code,
                "name": name,
                "resource": resource,
                "action": action,
                "description": description,
                "scope": scope
            })
            conn.commit()
            logger.info(f"✅ 成功创建权限: {code}")
    except Exception as e:
        logger.error(f"❌ 创建权限 {code} 失败: {str(e)}")


def create_missing_permissions():
    """创建缺失的权限"""
    logger.info("="*80)
    logger.info("创建缺失的权限")
    logger.info("="*80)
    
    missing_permissions = [
        # 线索跟进相关
        {
            "code": "lead_follow_up:create",
            "name": "创建线索跟进",
            "resource": "lead_follow_up",
            "action": "create",
            "description": "为线索添加跟进记录",
            "scope": None
        },
        
        # 商机查看自己
        {
            "code": "opportunity:view_own",
            "name": "查看自己的商机",
            "resource": "opportunity",
            "action": "view",
            "description": "查看自己负责的商机",
            "scope": "own"
        },
        
        # 客户查看自己
        {
            "code": "customer:view_own",
            "name": "查看自己的客户",
            "resource": "customer",
            "action": "view",
            "description": "查看自己负责的客户",
            "scope": "own"
        },
        
        # 客户联系人相关
        {
            "code": "customer_contact:create",
            "name": "创建客户联系人",
            "resource": "customer_contact",
            "action": "create",
            "description": "为客户添加联系人",
            "scope": None
        },
        {
            "code": "customer_contact:edit",
            "name": "编辑客户联系人",
            "resource": "customer_contact",
            "action": "edit",
            "description": "编辑客户联系人信息",
            "scope": None
        },
        
        # 客户跟进相关
        {
            "code": "customer_follow_up:create",
            "name": "创建客户跟进",
            "resource": "customer_follow_up",
            "action": "create",
            "description": "为客户添加跟进记录",
            "scope": None
        },
        {
            "code": "customer_follow_up:edit",
            "name": "编辑客户跟进",
            "resource": "customer_follow_up",
            "action": "edit",
            "description": "编辑客户跟进记录",
            "scope": None
        },
        
        # 回款计划查看所有
        {
            "code": "payment_plan:view_all",
            "name": "查看所有回款计划",
            "resource": "payment_plan",
            "action": "view",
            "description": "查看系统中所有回款计划",
            "scope": "all"
        },
        
        # 财务查看相关
        {
            "code": "finance:view_receivables",
            "name": "查看应收账款",
            "resource": "finance",
            "action": "view_receivables",
            "description": "查看应收账款分析",
            "scope": None
        },
        {
            "code": "finance:view_reports",
            "name": "查看财务报表",
            "resource": "finance",
            "action": "view_reports",
            "description": "查看财务报表",
            "scope": None
        },
        
        # 报表查看
        {
            "code": "report:view",
            "name": "查看报表",
            "resource": "report",
            "action": "view",
            "description": "查看系统报表",
            "scope": None
        },
        
        # 机会查看所有
        {
            "code": "opportunity:view_all",
            "name": "查看所有商机",
            "resource": "opportunity",
            "action": "view",
            "description": "查看系统中所有商机",
            "scope": "all"
        },
        
        # 客户查看所有
        {
            "code": "customer:view_all",
            "name": "查看所有客户",
            "resource": "customer",
            "action": "view",
            "description": "查看系统中所有客户",
            "scope": "all"
        }
    ]
    
    for perm in missing_permissions:
        create_permission(**perm)


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 创建缺失权限")
    logger.info("="*80)
    
    create_missing_permissions()
    
    logger.info("\n" + "="*80)
    logger.info("✅ 缺失权限创建完成！")
    logger.info("="*80)


if __name__ == "__main__":
    main()
