"""
完整的权限系统迁移脚本
包含系统中所有模块的权限定义和角色权限配置
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


def create_lead_permissions():
    """创建线索管理相关权限"""
    logger.info("\n" + "="*80)
    logger.info("创建线索管理相关权限")
    logger.info("="*80)
    
    permissions = [
        {
            "code": "lead:create",
            "name": "创建线索",
            "resource": "lead",
            "action": "create",
            "description": "创建新的线索",
            "scope": None
        },
        {
            "code": "lead:import",
            "name": "导入线索",
            "resource": "lead",
            "action": "import",
            "description": "批量导入线索",
            "scope": None
        },
        {
            "code": "lead:view_own",
            "name": "查看自己的线索",
            "resource": "lead",
            "action": "view",
            "description": "查看自己负责的线索",
            "scope": "own"
        },
        {
            "code": "lead:view_all",
            "name": "查看所有线索",
            "resource": "lead",
            "action": "view",
            "description": "查看系统中所有线索",
            "scope": "all"
        },
        {
            "code": "lead:edit_own",
            "name": "编辑自己的线索",
            "resource": "lead",
            "action": "edit",
            "description": "编辑自己负责的线索",
            "scope": "own"
        },
        {
            "code": "lead:edit_all",
            "name": "编辑所有线索",
            "resource": "lead",
            "action": "edit",
            "description": "编辑所有线索",
            "scope": "all"
        },
        {
            "code": "lead:delete_own",
            "name": "删除自己的线索",
            "resource": "lead",
            "action": "delete",
            "description": "删除自己负责的线索",
            "scope": "own"
        },
        {
            "code": "lead:delete_all",
            "name": "删除所有线索",
            "resource": "lead",
            "action": "delete",
            "description": "删除系统中所有线索",
            "scope": "all"
        },
        {
            "code": "lead:assign",
            "name": "分配线索",
            "resource": "lead",
            "action": "assign",
            "description": "将线索分配给其他销售",
            "scope": None
        },
        {
            "code": "lead:convert",
            "name": "转化线索",
            "resource": "lead",
            "action": "convert",
            "description": "将线索转化为客户",
            "scope": None
        },
        {
            "code": "lead:return_to_pool",
            "name": "退回线索到公海",
            "resource": "lead",
            "action": "return",
            "description": "将线索退回公海池",
            "scope": None
        },
        {
            "code": "lead:claim",
            "name": "领取线索",
            "resource": "lead",
            "action": "claim",
            "description": "从公海池领取线索",
            "scope": None
        },
        {
            "code": "lead:follow_up:create",
            "name": "创建线索跟进",
            "resource": "lead_follow_up",
            "action": "create",
            "description": "为线索添加跟进记录",
            "scope": None
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


def create_opportunity_permissions():
    """创建商机管理相关权限"""
    logger.info("\n" + "="*80)
    logger.info("创建商机管理相关权限")
    logger.info("="*80)
    
    permissions = [
        {
            "code": "opportunity:create",
            "name": "创建商机",
            "resource": "opportunity",
            "action": "create",
            "description": "创建新的商机",
            "scope": None
        },
        {
            "code": "opportunity:view_own",
            "name": "查看自己的商机",
            "resource": "opportunity",
            "action": "view",
            "description": "查看自己负责的商机",
            "scope": "own"
        },
        {
            "code": "opportunity:view_all",
            "name": "查看所有商机",
            "resource": "opportunity",
            "action": "view",
            "description": "查看系统中所有商机",
            "scope": "all"
        },
        {
            "code": "opportunity:edit_own",
            "name": "编辑自己的商机",
            "resource": "opportunity",
            "action": "edit",
            "description": "编辑自己负责的商机",
            "scope": "own"
        },
        {
            "code": "opportunity:edit_all",
            "name": "编辑所有商机",
            "resource": "opportunity",
            "action": "edit",
            "description": "编辑所有商机",
            "scope": "all"
        },
        {
            "code": "opportunity:delete_own",
            "name": "删除自己的商机",
            "resource": "opportunity",
            "action": "delete",
            "description": "删除自己负责的商机",
            "scope": "own"
        },
        {
            "code": "opportunity:win",
            "name": "商机赢单",
            "resource": "opportunity",
            "action": "win",
            "description": "将商机标记为赢单",
            "scope": None
        },
        {
            "code": "opportunity:lose",
            "name": "商机输单",
            "resource": "opportunity",
            "action": "lose",
            "description": "将商机标记为输单",
            "scope": None
        },
        {
            "code": "opportunity:assign",
            "name": "分配商机",
            "resource": "opportunity",
            "action": "assign",
            "description": "将商机分配给其他销售",
            "scope": None
        },
        {
            "code": "opportunity:stage:create",
            "name": "创建商机阶段",
            "resource": "opportunity_stage",
            "action": "create",
            "description": "创建商机阶段定义",
            "scope": None
        },
        {
            "code": "opportunity:stage:update",
            "name": "更新商机阶段",
            "resource": "opportunity_stage",
            "action": "edit",
            "description": "更新商机阶段定义",
            "scope": None
        },
        {
            "code": "opportunity:stage:delete",
            "name": "删除商机阶段",
            "resource": "opportunity_stage",
            "action": "delete",
            "description": "删除商机阶段定义",
            "scope": None
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


def create_customer_permissions():
    """创建客户管理相关权限"""
    logger.info("\n" + "="*80)
    logger.info("创建客户管理相关权限")
    logger.info("="*80)
    
    permissions = [
        {
            "code": "customer:create",
            "name": "创建客户",
            "resource": "customer",
            "action": "create",
            "description": "创建新的客户",
            "scope": None
        },
        {
            "code": "customer:view_own",
            "name": "查看自己的客户",
            "resource": "customer",
            "action": "view",
            "description": "查看自己负责的客户",
            "scope": "own"
        },
        {
            "code": "customer:view_all",
            "name": "查看所有客户",
            "resource": "customer",
            "action": "view",
            "description": "查看系统中所有客户",
            "scope": "all"
        },
        {
            "code": "customer:edit_own",
            "name": "编辑自己的客户",
            "resource": "customer",
            "action": "edit",
            "description": "编辑自己负责的客户",
            "scope": "own"
        },
        {
            "code": "customer:edit_all",
            "name": "编辑所有客户",
            "resource": "customer",
            "action": "edit",
            "description": "编辑所有客户",
            "scope": "all"
        },
        {
            "code": "customer:delete_own",
            "name": "删除自己的客户",
            "resource": "customer",
            "action": "delete",
            "description": "删除自己负责的客户",
            "scope": "own"
        },
        {
            "code": "customer:assign",
            "name": "分配客户",
            "resource": "customer",
            "action": "assign",
            "description": "将客户分配给其他销售",
            "scope": None
        },
        {
            "code": "customer:return_to_pool",
            "name": "退回客户到公海",
            "resource": "customer",
            "action": "return",
            "description": "将客户退回公海池",
            "scope": None
        },
        {
            "code": "customer:claim",
            "name": "领取客户",
            "resource": "customer",
            "action": "claim",
            "description": "从公海池领取客户",
            "scope": None
        },
        {
            "code": "customer:contact:create",
            "name": "创建客户联系人",
            "resource": "customer_contact",
            "action": "create",
            "description": "为客户添加联系人",
            "scope": None
        },
        {
            "code": "customer:contact:edit",
            "name": "编辑客户联系人",
            "resource": "customer_contact",
            "action": "edit",
            "description": "编辑客户联系人信息",
            "scope": None
        },
        {
            "code": "customer:contact:delete",
            "name": "删除客户联系人",
            "resource": "customer_contact",
            "action": "delete",
            "description": "删除客户联系人",
            "scope": None
        },
        {
            "code": "customer:follow_up:create",
            "name": "创建客户跟进",
            "resource": "customer_follow_up",
            "action": "create",
            "description": "为客户添加跟进记录",
            "scope": None
        },
        {
            "code": "customer:follow_up:edit",
            "name": "编辑客户跟进",
            "resource": "customer_follow_up",
            "action": "edit",
            "description": "编辑客户跟进记录",
            "scope": None
        },
        {
            "code": "customer:follow_up:delete",
            "name": "删除客户跟进",
            "resource": "customer_follow_up",
            "action": "delete",
            "description": "删除客户跟进记录",
            "scope": None
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


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
            "description": "查看自己创建的合同",
            "scope": "own"
        },
        {
            "code": "contract:view_all",
            "name": "查看所有合同",
            "resource": "contract",
            "action": "view",
            "description": "查看系统中所有合同",
            "scope": "all"
        },
        {
            "code": "contract:create",
            "name": "创建合同",
            "resource": "contract",
            "action": "create",
            "description": "创建新合同",
            "scope": None
        },
        {
            "code": "contract:edit_own",
            "name": "编辑自己的合同",
            "resource": "contract",
            "action": "edit",
            "description": "编辑自己创建的合同",
            "scope": "own"
        },
        {
            "code": "contract:edit_all",
            "name": "编辑所有合同",
            "resource": "contract",
            "action": "edit",
            "description": "编辑所有合同",
            "scope": "all"
        },
        {
            "code": "contract:delete_own",
            "name": "删除自己的合同",
            "resource": "contract",
            "action": "delete",
            "description": "删除自己创建的合同",
            "scope": "own"
        },
        {
            "code": "contract:approve_own",
            "name": "审批自己创建的合同",
            "resource": "contract",
            "action": "approve",
            "description": "审批自己创建的合同（特殊权限）",
            "scope": "own"
        },
        {
            "code": "contract:approve_all",
            "name": "审批所有合同",
            "resource": "contract",
            "action": "approve",
            "description": "审批所有合同",
            "scope": "all"
        },
        {
            "code": "contract:submit_approval",
            "name": "提交合同审批",
            "resource": "contract",
            "action": "submit_approval",
            "description": "提交合同进入审批流程",
            "scope": None
        },
        {
            "code": "contract:cancel_approval",
            "name": "撤回合同审批",
            "resource": "contract",
            "action": "cancel_approval",
            "description": "撤回合同审批流程",
            "scope": None
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
            "description": "创建新的发票申请",
            "scope": None
        },
        {
            "code": "invoice:approve",
            "name": "审批发票申请",
            "resource": "invoice",
            "action": "approve",
            "description": "审批发票申请（批准/拒绝）",
            "scope": None
        },
        {
            "code": "invoice:view_own",
            "name": "查看自己的发票",
            "resource": "invoice",
            "action": "view",
            "description": "查看自己创建的发票申请",
            "scope": "own"
        },
        {
            "code": "invoice:view_all",
            "name": "查看所有发票",
            "resource": "invoice",
            "action": "view",
            "description": "查看所有发票申请",
            "scope": "all"
        },
        {
            "code": "invoice:mark_issued",
            "name": "标记发票已开票",
            "resource": "invoice",
            "action": "mark_issued",
            "description": "将已批准的发票申请标记为已开票",
            "scope": None
        },
        {
            "code": "payment:plan:create",
            "name": "创建回款计划",
            "resource": "payment_plan",
            "action": "create",
            "description": "为合同创建回款计划",
            "scope": None
        },
        {
            "code": "payment:plan:edit",
            "name": "编辑回款计划",
            "resource": "payment_plan",
            "action": "edit",
            "description": "编辑回款计划",
            "scope": None
        },
        {
            "code": "payment:plan:delete",
            "name": "删除回款计划",
            "resource": "payment_plan",
            "action": "delete",
            "description": "删除回款计划",
            "scope": None
        },
        {
            "code": "payment:plan:view_all",
            "name": "查看所有回款计划",
            "resource": "payment_plan",
            "action": "view",
            "description": "查看所有回款计划",
            "scope": "all"
        },
        {
            "code": "payment:register",
            "name": "登记回款",
            "resource": "payment",
            "action": "register",
            "description": "登记回款记录",
            "scope": None
        },
        {
            "code": "payment:confirm",
            "name": "确认回款入账",
            "resource": "payment",
            "action": "confirm",
            "description": "财务确认回款入账",
            "scope": None
        },
        {
            "code": "payment:view_own",
            "name": "查看自己的回款",
            "resource": "payment",
            "action": "view",
            "description": "查看自己登记的回款",
            "scope": "own"
        },
        {
            "code": "payment:view_all",
            "name": "查看所有回款",
            "resource": "payment",
            "action": "view",
            "description": "查看所有回款记录",
            "scope": "all"
        },
        {
            "code": "finance:receivables_view",
            "name": "查看应收账款分析",
            "resource": "finance",
            "action": "view_receivables",
            "description": "查看应收账款账龄分析和逾期预警",
            "scope": None
        },
        {
            "code": "finance:reports_view",
            "name": "查看财务报表",
            "resource": "finance",
            "action": "view_reports",
            "description": "查看财务报表和统计分析",
            "scope": None
        },
        {
            "code": "finance:audit_logs",
            "name": "审计财务操作日志",
            "resource": "finance",
            "action": "audit_logs",
            "description": "查看财务相关的操作日志",
            "scope": None
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


def create_system_permissions():
    """创建系统管理相关权限"""
    logger.info("\n" + "="*80)
    logger.info("创建系统管理相关权限")
    logger.info("="*80)
    
    permissions = [
        {
            "code": "user:manage",
            "name": "管理用户",
            "resource": "user",
            "action": "manage",
            "description": "创建、编辑、删除用户",
            "scope": None
        },
        {
            "code": "role:manage",
            "name": "管理角色",
            "resource": "role",
            "action": "manage",
            "description": "创建、编辑、删除角色，分配权限",
            "scope": None
        },
        {
            "code": "permission:manage",
            "name": "管理权限",
            "resource": "permission",
            "action": "manage",
            "description": "创建、编辑、删除权限",
            "scope": None
        },
        {
            "code": "approval:flow:create",
            "name": "创建审批流程",
            "resource": "approval_flow",
            "action": "create",
            "description": "创建新的审批流程定义",
            "scope": None
        },
        {
            "code": "approval:flow:update",
            "name": "更新审批流程",
            "resource": "approval_flow",
            "action": "edit",
            "description": "更新审批流程定义",
            "scope": None
        },
        {
            "code": "statistics:view",
            "name": "查看统计数据",
            "resource": "statistics",
            "action": "view",
            "description": "查看系统统计报表",
            "scope": None
        }
    ]
    
    for perm in permissions:
        create_permission(**perm)


def assign_role_permissions():
    """为角色分配默认权限"""
    logger.info("\n" + "="*80)
    logger.info("为角色分配默认权限")
    logger.info("="*80)
    
    # 系统管理员权限
    admin_permissions = [
        # 线索管理
        "lead:create", "lead:import", "lead:view_all", "lead:edit_all", "lead:delete_own", "lead:delete_all",
        "lead:assign", "lead:convert", "lead:return_to_pool", "lead:claim", "lead:follow_up:create",
        # 商机管理
        "opportunity:create", "opportunity:view_all", "opportunity:edit_all", "opportunity:delete_own",
        "opportunity:win", "opportunity:lose", "opportunity:assign",
        "opportunity:stage:create", "opportunity:stage:update", "opportunity:stage:delete",
        # 客户管理
        "customer:create", "customer:view_all", "customer:edit_all", "customer:delete_own",
        "customer:assign", "customer:return_to_pool", "customer:claim",
        "customer:contact:create", "customer:contact:edit", "customer:contact:delete",
        "customer:follow_up:create", "customer:follow_up:edit", "customer:follow_up:delete",
        # 合同管理
        "contract:view_all", "contract:create", "contract:edit_all", "contract:delete_own",
        "contract:approve_all", "contract:approve_own", "contract:submit_approval", "contract:cancel_approval",
        # 发票管理
        "invoice:create", "invoice:approve", "invoice:view_all", "invoice:mark_issued",
        # 回款管理
        "payment:plan:create", "payment:plan:edit", "payment:plan:delete", "payment:plan:view_all",
        "payment:confirm", "payment:view_all", "payment:register",
        # 财务管理
        "finance:receivables_view", "finance:reports_view", "finance:audit_logs",
        # 系统管理
        "user:manage", "role:manage", "permission:manage",
        "approval:flow:create", "approval:flow:update", "statistics:view"
    ]
    
    # 销售总监权限
    sales_director_permissions = [
        # 线索管理
        "lead:create", "lead:import", "lead:view_all", "lead:edit_all", "lead:delete_own",
        "lead:assign", "lead:convert", "lead:return_to_pool", "lead:claim", "lead:follow_up:create",
        # 商机管理
        "opportunity:create", "opportunity:view_all", "opportunity:edit_all", "opportunity:delete_own",
        "opportunity:win", "opportunity:lose", "opportunity:assign",
        # 客户管理
        "customer:create", "customer:view_all", "customer:edit_all",
        "customer:assign", "customer:return_to_pool", "customer:claim",
        "customer:contact:create", "customer:contact:edit", "customer:contact:delete",
        "customer:follow_up:create", "customer:follow_up:edit", "customer:follow_up:delete",
        # 合同管理
        "contract:view_all", "contract:create", "contract:edit_all",
        "contract:approve_own", "contract:submit_approval", "contract:cancel_approval",
        # 发票管理
        "invoice:create", "invoice:view_all",
        # 回款管理
        "payment:plan:create", "payment:plan:edit", "payment:plan:view_all",
        "payment:view_all", "payment:register",
        # 统计
        "statistics:view"
    ]
    
    # 销售成员权限
    sales_member_permissions = [
        # 线索管理
        "lead:create", "lead:view_own", "lead:edit_own", "lead:delete_own",
        "lead:convert", "lead:claim", "lead:follow_up:create",
        # 商机管理
        "opportunity:create", "opportunity:view_own", "opportunity:edit_own",
        # 客户管理
        "customer:create", "customer:view_own", "customer:edit_own",
        "customer:claim",
        "customer:contact:create", "customer:contact:edit",
        "customer:follow_up:create", "customer:follow_up:edit",
        # 合同管理
        "contract:view_own", "contract:create", "contract:edit_own",
        "contract:submit_approval", "contract:cancel_approval",
        # 发票管理
        "invoice:create",
        # 回款管理
        "payment:register"
    ]
    
    # 财务人员权限
    finance_permissions = [
        # 基础查看权限
        "lead:view_all", "opportunity:view_all", "customer:view_all",
        # 合同管理
        "contract:view_all",
        # 发票管理
        "invoice:approve", "invoice:view_all", "invoice:mark_issued",
        # 回款管理
        "payment:plan:view_all", "payment:confirm", "payment:view_all",
        # 财务管理
        "finance:receivables_view", "finance:reports_view", "finance:audit_logs",
        # 统计
        "statistics:view"
    ]
    
    role_permission_map = {
        "TEAM_ADMIN": admin_permissions,
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
    logger.info("飞书轻量化CRM - 完整权限系统迁移")
    logger.info("="*80)
    
    create_lead_permissions()
    create_opportunity_permissions()
    create_customer_permissions()
    create_contract_permissions()
    create_finance_permissions()
    create_system_permissions()
    assign_role_permissions()
    
    logger.info("\n" + "="*80)
    logger.info("✅ 权限迁移完成！")
    logger.info("="*80)
    logger.info("\n权限统计:")
    logger.info("- 线索管理: 12个权限")
    logger.info("- 商机管理: 12个权限")
    logger.info("- 客户管理: 16个权限")
    logger.info("- 合同管理: 10个权限")
    logger.info("- 财务管理: 17个权限")
    logger.info("- 系统管理: 6个权限")
    logger.info("- 总计: 73个权限")


if __name__ == "__main__":
    main()
