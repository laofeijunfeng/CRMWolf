"""
重新分配角色权限（使用正确的权限代码）
"""
import logging
from sqlalchemy import create_engine, text
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_engine(settings.get_database_url())


# 权限代码映射表
PERMISSION_CODE_MAPPING = {
    # 线索管理
    "lead_follow_up:create": "lead:follow_up:create",
    "lead:return_to_pool": "lead:return",
    
    # 商机管理
    "opportunity:view_own": "opportunity:view:own",
    "opportunity:view_all": "opportunity:view:all",
    "opportunity:edit_own": "opportunity:edit:own",
    "opportunity:edit_all": "opportunity:edit:all",
    "opportunity:delete_own": "opportunity:delete:own",
    "opportunity_stage:create": "opportunity:stage:create",
    "opportunity_stage:edit": "opportunity:stage:edit",
    "opportunity_stage:delete": "opportunity:stage:delete",
    "opportunity_stage:manage": "opportunity:analytics:view",
    
    # 客户管理
    "customer:view_own": "customer:view:own",
    "customer:view_all": "customer:view:all",
    "customer:edit_own": "customer:edit:own",
    "customer:edit_all": "customer:edit:all",
    "customer:delete_own": "customer:delete:own",
    "customer:return_to_pool": "customer:return",
    "customer_contact:create": "customer:contact:create",
    "customer_contact:edit": "customer:contact:edit",
    "customer_contact:delete": "customer:contact:delete",
    "customer_follow_up:create": "customer:follow_up:create",
    "customer_follow_up:edit": "customer:follow_up:edit",
    "customer_follow_up:delete": "customer:follow_up:delete",
    
    # 合同管理
    "contract:view_own": "contract:view_own",
    "contract:view_all": "contract:view_all",
    "contract:edit_own": "contract:edit_own",
    "contract:edit_all": "contract:edit_all",
    "contract:delete_own": "contract:delete_own",
    "contract:approve_all": "contract:approve_all",
    "contract:approve_own": "contract:approve_own",
    "contract:submit_approval": "contract:submit_approval",
    "contract:cancel_approval": "contract:cancel_approval",
    
    # 发票管理
    "invoice:create": "invoice:create",
    "invoice:approve": "invoice:approve",
    "invoice:view_own": "invoice:view_own",
    "invoice:view_all": "invoice:view_all",
    "invoice:mark_issued": "invoice:mark_issued",
    
    # 回款管理
    "payment_plan:create": "payment:plan:create",
    "payment_plan:edit": "payment:plan:edit",
    "payment_plan:delete": "payment:plan:delete",
    "payment_plan:view_own": "payment:plan:view_own",
    "payment_plan:view_all": "payment:plan:view_all",
    "payment:confirm": "payment:confirm",
    "payment:register": "payment:register",
    "payment:view_own": "payment:view_own",
    "payment:view_all": "payment:view_all",
    
    # 财务管理
    "finance:receivables_view": "finance:receivables_view",
    "finance:reports_view": "finance:reports_view",
    "finance:audit_logs": "finance:audit_logs",
    
    # 系统管理
    "user:manage": "user:manage",
    "role:manage": "role:manage",
    "permission:manage": "permission:manage",
    "approval_flow:create": "approval:flow:create",
    "approval_flow:update": "approval:flow:update",
    "statistics:view": "statistics:view",
    "report:view": "report:view"
}


def get_permission_id_by_code(code: str) -> int:
    """根据权限代码获取权限ID"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id FROM permissions WHERE code = '{code}'
            """))
            row = result.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"获取权限ID失败: {str(e)}")
        return None


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


def check_role_permission_exists(role_id: int, permission_id: int) -> bool:
    """检查角色权限关联是否存在"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as count FROM role_permissions
                WHERE role_id = {role_id} AND permission_id = {permission_id}
            """))
            return result.fetchone()[0] > 0
    except Exception as e:
        logger.error(f"检查角色权限关联失败: {str(e)}")
        return False


def map_permission_code(code: str) -> str:
    """映射权限代码到数据库中的实际代码"""
    return PERMISSION_CODE_MAPPING.get(code, code)


def assign_permission_to_role(role_code: str, permission_code: str):
    """为角色分配权限"""
    role_id = get_role_id_by_code(role_code)
    if not role_id:
        logger.warning(f"⚠️  角色 {role_code} 不存在，跳过权限分配")
        return False
    
    actual_code = map_permission_code(permission_code)
    permission_id = get_permission_id_by_code(actual_code)
    if not permission_id:
        logger.warning(f"⚠️  权限 {permission_code} (映射为 {actual_code}) 不存在，跳过分配")
        return False
    
    try:
        if check_role_permission_exists(role_id, permission_id):
            logger.info(f"✅ 角色 {role_code} 已拥有权限 {permission_code} (实际: {actual_code})")
            return True
        
        with engine.connect() as conn:
            insert_sql = text("""
                INSERT INTO role_permissions (role_id, permission_id, created_at)
                VALUES (:role_id, :permission_id, NOW())
            """)
            conn.execute(insert_sql, {
                "role_id": role_id,
                "permission_id": permission_id
            })
            conn.commit()
            logger.info(f"✅ 成功为角色 {role_code} 分配权限 {permission_code} (实际: {actual_code})")
            return True
    except Exception as e:
        logger.error(f"❌ 为角色 {role_code} 分配权限 {permission_code} 失败: {str(e)}")
        return False


def assign_system_admin_permissions():
    """为系统管理员分配权限"""
    logger.info("\n" + "="*80)
    logger.info("为系统管理员分配权限")
    logger.info("="*80)
    
    permissions = [
        # 线索管理（12个）
        "lead:create", "lead:import", "lead:view_own", "lead:view_all",
        "lead:edit_own", "lead:edit_all", "lead:delete_own",
        "lead:assign", "lead:convert", "lead:return_to_pool", "lead:claim",
        "lead_follow_up:create",
        
        # 商机管理（12个）
        "opportunity:create", "opportunity:view_own", "opportunity:view_all",
        "opportunity:edit_own", "opportunity:edit_all", "opportunity:delete_own",
        "opportunity:win", "opportunity:lose", "opportunity:assign",
        "opportunity_stage:create", "opportunity_stage:edit", "opportunity_stage:delete",
        
        # 客户管理（16个）
        "customer:create", "customer:view_own", "customer:view_all",
        "customer:edit_own", "customer:edit_all", "customer:delete_own",
        "customer:assign", "customer:return_to_pool", "customer:claim",
        "customer_contact:create", "customer_contact:edit", "customer_contact:delete",
        "customer_follow_up:create", "customer_follow_up:edit", "customer_follow_up:delete",
        "customer:update",
        
        # 合同管理（10个）
        "contract:view_own", "contract:view_all", "contract:create",
        "contract:edit_own", "contract:edit_all", "contract:delete_own",
        "contract:approve_all", "contract:approve_own",
        "contract:submit_approval", "contract:cancel_approval",
        
        # 发票管理（5个）
        "invoice:create", "invoice:approve", "invoice:view_own", "invoice:view_all",
        "invoice:mark_issued",
        
        # 回款管理（6个）
        "payment_plan:create", "payment_plan:edit", "payment_plan:delete",
        "payment_plan:view_own", "payment_plan:view_all",
        "payment:confirm",
        
        # 财务管理（6个）
        "payment:view_own", "payment:view_all", "payment:register",
        "finance:receivables_view", "finance:reports_view", "finance:audit_logs",
        
        # 系统管理（6个）
        "user:manage", "role:manage", "permission:manage",
        "approval_flow:create", "approval_flow:update",
        "statistics:view", "report:view"
    ]
    
    success_count = 0
    for perm_code in permissions:
        if assign_permission_to_role("TEAM_ADMIN", perm_code):
            success_count += 1
    
    logger.info(f"\n系统管理员权限分配完成: {success_count}/{len(permissions)}")
    return success_count


def assign_sales_director_permissions():
    """为销售总监分配权限"""
    logger.info("\n" + "="*80)
    logger.info("为销售总监分配权限")
    logger.info("="*80)
    
    permissions = [
        # 线索管理（10个）
        "lead:create", "lead:import", "lead:view_all", "lead:edit_all",
        "lead:delete_own", "lead:assign", "lead:convert", "lead:return_to_pool",
        "lead:claim", "lead_follow_up:create",
        
        # 商机管理（9个）
        "opportunity:create", "opportunity:view_all", "opportunity:edit_all",
        "opportunity:delete_own", "opportunity:win", "opportunity:lose",
        "opportunity:assign",
        "opportunity_stage:create", "opportunity_stage:edit",
        
        # 客户管理（15个）
        "customer:create", "customer:view_all", "customer:edit_all",
        "customer:assign", "customer:return_to_pool", "customer:claim",
        "customer_contact:create", "customer_contact:edit", "customer_contact:delete",
        "customer_follow_up:create", "customer_follow_up:edit", "customer_follow_up:delete",
        "customer:update",
        
        # 合同管理（7个）
        "contract:view_all", "contract:create", "contract:edit_all",
        "contract:approve_own", "contract:submit_approval", "contract:cancel_approval",
        
        # 发票管理（3个）
        "invoice:create", "invoice:view_all",
        
        # 回款管理（4个）
        "payment_plan:create", "payment_plan:edit", "payment_plan:view_all",
        
        # 财务管理（1个）
        "payment:register",
        
        # 统计
        "statistics:view"
    ]
    
    success_count = 0
    for perm_code in permissions:
        if assign_permission_to_role("SALES_DIRECTOR", perm_code):
            success_count += 1
    
    logger.info(f"\n销售总监权限分配完成: {success_count}/{len(permissions)}")
    return success_count


def assign_sales_member_permissions():
    """为销售成员分配权限"""
    logger.info("\n" + "="*80)
    logger.info("为销售成员分配权限")
    logger.info("="*80)
    
    permissions = [
        # 线索管理（7个）
        "lead:create", "lead:view_own", "lead:edit_own", "lead:delete_own",
        "lead:convert", "lead:claim", "lead_follow_up:create",
        
        # 商机管理（4个）
        "opportunity:create", "opportunity:view_own", "opportunity:edit_own",
        
        # 客户管理（8个）
        "customer:create", "customer:view_own", "customer:edit_own",
        "customer:claim",
        "customer_contact:create", "customer_contact:edit",
        "customer_follow_up:create", "customer_follow_up:edit",
        
        # 合同管理（5个）
        "contract:view_own", "contract:create", "contract:edit_own",
        "contract:submit_approval", "contract:cancel_approval",
        
        # 发票管理（1个）
        "invoice:create",
        
        # 回款管理（1个）
        "payment:register"
    ]
    
    success_count = 0
    for perm_code in permissions:
        if assign_permission_to_role("SALES_MEMBER", perm_code):
            success_count += 1
    
    logger.info(f"\n销售成员权限分配完成: {success_count}/{len(permissions)}")
    return success_count


def assign_finance_permissions():
    """为财务人员分配权限"""
    logger.info("\n" + "="*80)
    logger.info("为财务人员分配权限")
    logger.info("="*80)
    
    permissions = [
        # 基础查看权限（3个）
        "lead:view_all", "opportunity:view_all", "customer:view_all",
        
        # 合同管理（1个）
        "contract:view_all",
        
        # 发票管理（4个）
        "invoice:approve", "invoice:view_all", "invoice:mark_issued",
        
        # 回款管理（5个）
        "payment_plan:view_all", "payment:confirm", "payment:view_all",
        
        # 财务管理（6个）
        "finance:receivables_view", "finance:reports_view", "finance:audit_logs",
        
        # 统计
        "statistics:view", "report:view"
    ]
    
    success_count = 0
    for perm_code in permissions:
        if assign_permission_to_role("finance", perm_code):
            success_count += 1
    
    logger.info(f"\n财务人员权限分配完成: {success_count}/{len(permissions)}")
    return success_count


def verify_role_permissions():
    """验证角色权限分配"""
    logger.info("\n" + "="*80)
    logger.info("验证角色权限分配结果")
    logger.info("="*80)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT r.code, r.name, COUNT(rp.permission_id) as perm_count
                FROM roles r
                LEFT JOIN role_permissions rp ON r.id = rp.role_id
                GROUP BY r.id, r.code, r.name
                ORDER BY r.code
            """))
            
            for row in result:
                logger.info(f"\n{row[0]} ({row[1]}): {row[2]}个权限")
    except Exception as e:
        logger.error(f"❌ 验证角色权限分配失败: {str(e)}")


def main():
    logger.info("="*80)
    logger.info("飞书轻量化CRM - 角色权限重新分配")
    logger.info("="*80)
    
    total_assigned = 0
    total_assigned += assign_system_admin_permissions()
    total_assigned += assign_sales_director_permissions()
    total_assigned += assign_sales_member_permissions()
    total_assigned += assign_finance_permissions()
    
    logger.info("\n" + "="*80)
    logger.info(f"✅ 权限分配完成！总共分配 {total_assigned} 个权限")
    logger.info("="*80)
    
    verify_role_permissions()


if __name__ == "__main__":
    main()
