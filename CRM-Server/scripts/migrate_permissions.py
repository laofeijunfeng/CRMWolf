import logging
from sqlalchemy import create_engine, text
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_engine(str(settings.DATABASE_URL))


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


def get_role_id_by_code(role_code: str) -> int:
    """根据角色代码获取角色ID"""
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
    """创建权限"""
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
    """为角色分配权限"""
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


def create_contract_permissions():
    """创建合同管理相关权限"""
    logger.info("\n" + "="*80)
    logger.info("创建合同管理相关权限")
    logger.info("="*80)
    
    permissions = [
        {
            "code": "contract:view_own",
            "name": "查看自己的合同",
            "resource": "contract",
            "action": "view",
            "description": "查看自己创建的合同"
        },
        {
            "code": "contract:view_all",
            "name": "查看所有合同",
            "resource": "contract",
            "action": "view",
            "description": "查看系统中所有合同"
        },
        {
            "code": "contract:create",
            "name": "创建合同",
            "resource": "contract",
            "action": "create",
            "description": "创建新合同"
        },
        {
            "code": "contract:edit_own",
            "name": "编辑自己的合同",
            "resource": "contract",
            "action": "edit",
            "description": "编辑自己创建的合同"
        },
        {
            "code": "contract:edit_all",
            "name": "编辑所有合同",
            "resource": "contract",
            "action": "edit",
            "description": "编辑所有合同"
        },
        {
            "code": "contract:delete_own",
            "name": "删除自己的合同",
            "resource": "contract",
            "action": "delete",
            "description": "删除自己创建的合同"
        },
        {
            "code": "contract:approve_own",
            "name": "审批自己创建的合同",
            "resource": "contract",
            "action": "approve",
            "description": "审批自己创建的合同（特殊权限，仅销售总监和管理员可用）"
        },
        {
            "code": "contract:approve_all",
            "name": "审批所有合同",
            "resource": "contract",
            "action": "approve",
            "description": "审批所有合同"
        },
        {
            "code": "contract:submit_approval",
            "name": "提交合同审批",
            "resource": "contract",
            "action": "submit_approval",
            "description": "提交合同进入审批流程"
        },
        {
            "code": "contract:cancel_approval",
            "name": "撤回合同审批",
            "resource": "contract",
            "action": "cancel_approval",
            "description": "撤回合同审批流程"
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


def create_finance_permissions():
    """创建财务管理相关权限"""
    logger.info("\n" + "="*80)
    logger.info("创建财务管理相关权限")
    logger.info("="*80)
    
    permissions = [
        {
            "code": "invoice:create",
            "name": "创建发票申请",
            "resource": "invoice",
            "action": "create",
            "description": "创建新的发票申请"
        },
        {
            "code": "invoice:approve",
            "name": "审批发票申请",
            "resource": "invoice",
            "action": "approve",
            "description": "审批发票申请（批准/拒绝）"
        },
        {
            "code": "invoice:view_all",
            "name": "查看所有发票",
            "resource": "invoice",
            "action": "view",
            "description": "查看所有发票申请"
        },
        {
            "code": "invoice:mark_issued",
            "name": "标记发票已开票",
            "resource": "invoice",
            "action": "mark_issued",
            "description": "将已批准的发票申请标记为已开票"
        },
        {
            "code": "payment:confirm",
            "name": "确认回款入账",
            "resource": "payment",
            "action": "confirm",
            "description": "财务确认回款入账"
        },
        {
            "code": "payment:view_all",
            "name": "查看所有回款",
            "resource": "payment",
            "action": "view",
            "description": "查看所有回款记录"
        },
        {
            "code": "payment:register",
            "name": "登记回款",
            "resource": "payment",
            "action": "register",
            "description": "登记回款记录"
        },
        {
            "code": "finance:receivables_view",
            "name": "查看应收账款分析",
            "resource": "finance",
            "action": "view_receivables",
            "description": "查看应收账款账龄分析和逾期预警"
        },
        {
            "code": "finance:reports_view",
            "name": "查看财务报表",
            "resource": "finance",
            "action": "view_reports",
            "description": "查看财务报表和统计分析"
        },
        {
            "code": "finance:audit_logs",
            "name": "审计财务操作日志",
            "resource": "finance",
            "action": "audit_logs",
            "description": "查看财务相关的操作日志"
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


def assign_default_permissions():
    """为角色分配默认权限"""
    logger.info("\n" + "="*80)
    logger.info("为角色分配默认权限")
    logger.info("="*80)
    
    admin_permissions = [
        "contract:view_all",
        "contract:create",
        "contract:edit_all",
        "contract:delete_own",
        "contract:approve_all",
        "contract:approve_own",
        "contract:submit_approval",
        "contract:cancel_approval",
        "invoice:create",
        "invoice:approve",
        "invoice:view_all",
        "invoice:mark_issued",
        "payment:confirm",
        "payment:view_all",
        "payment:register",
        "finance:receivables_view",
        "finance:reports_view",
        "finance:audit_logs"
    ]
    
    sales_director_permissions = [
        "contract:view_all",
        "contract:create",
        "contract:edit_all",
        "contract:approve_own",
        "contract:submit_approval",
        "contract:cancel_approval",
        "invoice:create",
        "invoice:view_all",
        "payment:view_all",
        "payment:register"
    ]
    
    sales_member_permissions = [
        "contract:view_own",
        "contract:create",
        "contract:edit_own",
        "contract:submit_approval",
        "contract:cancel_approval",
        "invoice:create",
        "payment:register"
    ]
    
    finance_permissions = [
        "contract:view_all",
        "invoice:approve",
        "invoice:view_all",
        "invoice:mark_issued",
        "payment:confirm",
        "payment:view_all",
        "finance:receivables_view",
        "finance:reports_view",
        "finance:audit_logs"
    ]
    
    role_permission_map = {
        "SYSTEM_ADMIN": admin_permissions,
        "SALES_DIRECTOR": sales_director_permissions,
        "SALES_MEMBER": sales_member_permissions,
        "finance": finance_permissions
    }
    
    for role_code, permissions in role_permission_map.items():
        logger.info(f"\n为角色 {role_code} 分配权限:")
        for perm_code in permissions:
            assign_permission_to_role(role_code, perm_code)


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 权限系统迁移")
    logger.info("="*80)
    
    create_contract_permissions()
    create_finance_permissions()
    assign_default_permissions()
    
    logger.info("\n" + "="*80)
    logger.info("✅ 权限迁移完成！")
    logger.info("="*80)


if __name__ == "__main__":
    main()
