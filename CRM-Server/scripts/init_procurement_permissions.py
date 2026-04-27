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
    logger.error("环境变量DATABASE_URL未设置，请先设置环境变量")
    logger.error("例如: export DATABASE_URL='mysql+pymysql://user:password@host:port/dbname'")
    sys.exit(1)

engine = create_engine(DATABASE_URL)


def check_permission_exists(code: str) -> bool:
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


def get_role_id_by_code(role_code: str) -> int:
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id FROM roles WHERE code = '{role_code}'
            """))
            row = result.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"获取角色ID失败: {str(e)}")
        return None


def create_permission(code: str, name: str, resource: str, action: str, description: str):
    if check_permission_exists(code):
        logger.info(f"✅ 权限 {code} 已存在，跳过创建")
        return
    
    try:
        with engine.connect() as conn:
            insert_sql = text("""
                INSERT INTO permissions (code, name, resource, action, description, created_at, updated_at)
                VALUES (:code, :name, :resource, :action, :description, NOW(), NOW())
            """)
            conn.execute(insert_sql, {
                "code": code,
                "name": name,
                "resource": resource,
                "action": action,
                "description": description
            })
            conn.commit()
            logger.info(f"✅ 成功创建权限: {code}")
    except Exception as e:
        logger.error(f"❌ 创建权限 {code} 失败: {str(e)}")


def assign_permission_to_role(role_code: str, permission_code: str):
    role_id = get_role_id_by_code(role_code)
    if not role_id:
        logger.warning(f"⚠️  角色 {role_code} 不存在，跳过权限分配")
        return
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id FROM permissions WHERE code = '{permission_code}'
            """))
            permission_row = result.fetchone()
            if not permission_row:
                logger.warning(f"⚠️  权限 {permission_code} 不存在，跳过分配")
                return
            
            permission_id = permission_row[0]
            
            existing = conn.execute(text(f"""
                SELECT COUNT(*) as count FROM role_permissions
                WHERE role_id = {role_id} AND permission_id = {permission_id}
            """))
            
            if existing.fetchone()[0] > 0:
                logger.info(f"✅ 角色 {role_code} 已拥有权限 {permission_code}，跳过分配")
                return
            
            insert_sql = text("""
                INSERT INTO role_permissions (role_id, permission_id, created_at)
                VALUES (:role_id, :permission_id, NOW())
            """)
            conn.execute(insert_sql, {
                "role_id": role_id,
                "permission_id": permission_id
            })
            conn.commit()
            logger.info(f"✅ 成功为角色 {role_code} 分配权限 {permission_code}")
    except Exception as e:
        logger.error(f"❌ 为角色 {role_code} 分配权限 {permission_code} 失败: {str(e)}")


def create_procurement_permissions():
    logger.info("\n" + "="*80)
    logger.info("创建采购管理相关权限")
    logger.info("="*80)
    
    permissions = [
        {
            "code": "procurement_method:view",
            "name": "查看采购方式",
            "resource": "procurement_method",
            "action": "view",
            "description": "查看采购方式列表和详情"
        },
        {
            "code": "procurement_method:create",
            "name": "创建采购方式",
            "resource": "procurement_method",
            "action": "create",
            "description": "创建新的采购方式"
        },
        {
            "code": "procurement_method:update",
            "name": "更新采购方式",
            "resource": "procurement_method",
            "action": "update",
            "description": "更新采购方式信息"
        },
        {
            "code": "procurement_method:delete",
            "name": "删除采购方式",
            "resource": "procurement_method",
            "action": "delete",
            "description": "删除采购方式"
        },
        {
            "code": "procurement_stage:view",
            "name": "查看阶段模板",
            "resource": "procurement_stage",
            "action": "view",
            "description": "查看采购阶段模板"
        },
        {
            "code": "procurement_stage:create",
            "name": "创建阶段模板",
            "resource": "procurement_stage",
            "action": "create",
            "description": "创建新的采购阶段模板"
        },
        {
            "code": "procurement_stage:update",
            "name": "更新阶段模板",
            "resource": "procurement_stage",
            "action": "update",
            "description": "更新采购阶段模板"
        },
        {
            "code": "procurement_stage:delete",
            "name": "删除阶段模板",
            "resource": "procurement_stage",
            "action": "delete",
            "description": "删除采购阶段模板"
        },
        {
            "code": "procurement:admin:assess",
            "name": "采购管理-影响评估",
            "resource": "procurement_admin",
            "action": "assess",
            "description": "评估阶段模板变更影响范围"
        },
        {
            "code": "procurement:admin:migrate",
            "name": "采购管理-批量迁移",
            "resource": "procurement_admin",
            "action": "migrate",
            "description": "批量迁移商机采购方式"
        },
        {
            "code": "procurement:admin:rollback",
            "name": "采购管理-版本回滚",
            "resource": "procurement_admin",
            "action": "rollback",
            "description": "回滚阶段模板到指定版本"
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


def assign_default_permissions():
    logger.info("\n" + "="*80)
    logger.info("为角色分配采购管理默认权限")
    logger.info("="*80)
    
    admin_permissions = [
        "procurement_method:view",
        "procurement_method:create",
        "procurement_method:update",
        "procurement_method:delete",
        "procurement_stage:view",
        "procurement_stage:create",
        "procurement_stage:update",
        "procurement_stage:delete",
        "procurement:admin:assess",
        "procurement:admin:migrate",
        "procurement:admin:rollback"
    ]
    
    sales_director_permissions = [
        "procurement_method:view",
        "procurement_stage:view",
        "procurement:admin:assess"
    ]
    
    sales_member_permissions = [
        "procurement_method:view",
        "procurement_stage:view"
    ]
    
    role_permission_map = {
        "SYSTEM_ADMIN": admin_permissions,
        "SALES_DIRECTOR": sales_director_permissions,
        "SALES_MEMBER": sales_member_permissions
    }
    
    for role_code, permissions in role_permission_map.items():
        logger.info(f"\n为角色 {role_code} 分配权限:")
        for perm_code in permissions:
            assign_permission_to_role(role_code, perm_code)


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 采购管理模块权限初始化")
    logger.info("="*80)
    
    create_procurement_permissions()
    assign_default_permissions()
    
    logger.info("\n" + "="*80)
    logger.info("✅ 采购管理权限初始化完成！")
    logger.info("="*80)


if __name__ == "__main__":
    main()
