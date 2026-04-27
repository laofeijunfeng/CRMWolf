from app.core.database import engine, Base, SessionLocal
from app.models import User, Role, Permission, UserRole, RolePermission, Lead, LeadFollowUp
from app.models.customer import Customer, Contact
from app.models.customer_follow_up import CustomerFollowUp
from app.crud.role import role_crud
from app.crud.permission import permission_crud
from app.schemas.role import RoleCreate
from app.schemas.permission import PermissionCreate


def init_database():
    Base.metadata.create_all(bind=engine)
    print("数据库表创建成功")


def init_roles_and_permissions():
    db = SessionLocal()
    try:
        existing_roles = db.query(Role).count()
        if existing_roles > 0:
            print("角色和权限已初始化，跳过")
            return

        roles_data = [
            {
                "name": "销售总监",
                "code": "SALES_DIRECTOR",
                "description": "销售总监，可以查看团队所有客户数据和报表"
            },
            {
                "name": "销售成员",
                "code": "SALES_MEMBER",
                "description": "销售成员，只能查看和操作自己创建的客户"
            },
            {
                "name": "系统管理员",
                "code": "SYSTEM_ADMIN",
                "description": "系统管理员，负责系统配置和维护"
            }
        ]

        created_roles = {}
        for role_data in roles_data:
            role = role_crud.create(db, RoleCreate(**role_data))
            created_roles[role.code] = role
            print(f"创建角色: {role.name}")

        permissions_data = [
            {
                "name": "查看所有客户",
                "code": "customer:view:all",
                "resource": "customer",
                "action": "view",
                "scope": "all",
                "description": "查看所有客户的权限"
            },
            {
                "name": "查看自己的客户",
                "code": "customer:view:own",
                "resource": "customer",
                "action": "view",
                "scope": "own",
                "description": "查看自己负责的客户的权限"
            },
            {
                "name": "创建客户",
                "code": "customer:create",
                "resource": "customer",
                "action": "create",
                "scope": None,
                "description": "创建客户的权限"
            },
            {
                "name": "编辑客户",
                "code": "customer:update",
                "resource": "customer",
                "action": "update",
                "scope": None,
                "description": "编辑客户的权限"
            },
            {
                "name": "删除客户",
                "code": "customer:delete",
                "resource": "customer",
                "action": "delete",
                "scope": None,
                "description": "删除客户的权限"
            },
            {
                "name": "转化线索",
                "code": "customer:convert",
                "resource": "customer",
                "action": "convert",
                "scope": None,
                "description": "将线索转化为客户的权限"
            },
            {
                "name": "更新客户状态",
                "code": "customer:status",
                "resource": "customer",
                "action": "status",
                "scope": None,
                "description": "更新客户状态的权限"
            },
            {
                "name": "管理联系人",
                "code": "contact:manage",
                "resource": "contact",
                "action": "manage",
                "scope": None,
                "description": "管理联系人的权限"
            },
            {
                "name": "创建客户跟进记录",
                "code": "customer:followup:create",
                "resource": "customer",
                "action": "followup",
                "scope": None,
                "description": "为客户创建跟进记录的权限"
            },
            {
                "name": "查看客户跟进记录",
                "code": "customer:followup:view",
                "resource": "customer",
                "action": "followup",
                "scope": None,
                "description": "查看客户跟进记录的权限"
            },
            {
                "name": "删除客户跟进记录",
                "code": "customer:followup:delete",
                "resource": "customer",
                "action": "followup",
                "scope": None,
                "description": "删除客户跟进记录的权限"
            },
            {
                "name": "查看所有商机",
                "code": "opportunity:view:all",
                "resource": "opportunity",
                "action": "view",
                "scope": "all",
                "description": "查看所有商机的权限"
            },
            {
                "name": "查看自己的商机",
                "code": "opportunity:view:own",
                "resource": "opportunity",
                "action": "view",
                "scope": "own",
                "description": "查看自己负责的商机的权限"
            },
            {
                "name": "创建商机",
                "code": "opportunity:create",
                "resource": "opportunity",
                "action": "create",
                "scope": None,
                "description": "创建商机的权限"
            },
            {
                "name": "编辑商机",
                "code": "opportunity:update",
                "resource": "opportunity",
                "action": "update",
                "scope": None,
                "description": "编辑商机的权限"
            },
            {
                "name": "删除商机",
                "code": "opportunity:delete",
                "resource": "opportunity",
                "action": "delete",
                "scope": None,
                "description": "删除商机的权限"
            },
            {
                "name": "推进商机阶段",
                "code": "opportunity:stage",
                "resource": "opportunity",
                "action": "stage",
                "scope": None,
                "description": "推进或退回商机阶段的权限"
            },
            {
                "name": "标记商机赢单",
                "code": "opportunity:win",
                "resource": "opportunity",
                "action": "win",
                "scope": None,
                "description": "标记商机为赢单的权限"
            },
            {
                "name": "标记商机输单",
                "code": "opportunity:lose",
                "resource": "opportunity",
                "action": "lose",
                "scope": None,
                "description": "标记商机为输单的权限"
            },
            {
                "name": "管理销售阶段",
                "code": "opportunity:stage:manage",
                "resource": "opportunity_stage",
                "action": "manage",
                "scope": None,
                "description": "管理销售阶段的权限"
            },
            {
                "name": "查看商机分析",
                "code": "opportunity:analytics:view",
                "resource": "opportunity",
                "action": "analytics",
                "scope": None,
                "description": "查看商机销售漏斗和分析的权限"
            },
            {
                "name": "查看团队报表",
                "code": "report:view:team",
                "resource": "report",
                "action": "view",
                "scope": "team",
                "description": "查看团队报表的权限"
            },
            {
                "name": "查看所有线索",
                "code": "lead:view:all",
                "resource": "lead",
                "action": "view",
                "scope": "all",
                "description": "查看所有线索的权限"
            },
            {
                "name": "查看自己的线索",
                "code": "lead:view:own",
                "resource": "lead",
                "action": "view",
                "scope": "own",
                "description": "查看自己负责的线索的权限"
            },
            {
                "name": "创建线索",
                "code": "lead:create",
                "resource": "lead",
                "action": "create",
                "scope": None,
                "description": "创建线索的权限"
            },
            {
                "name": "编辑线索",
                "code": "lead:update",
                "resource": "lead",
                "action": "update",
                "scope": None,
                "description": "编辑线索的权限"
            },
            {
                "name": "删除线索",
                "code": "lead:delete",
                "resource": "lead",
                "action": "delete",
                "scope": None,
                "description": "删除线索的权限"
            },
            {
                "name": "分配线索",
                "code": "lead:assign",
                "resource": "lead",
                "action": "assign",
                "scope": None,
                "description": "分配线索给其他销售成员的权限"
            },
            {
                "name": "领取线索",
                "code": "lead:claim",
                "resource": "lead",
                "action": "claim",
                "scope": None,
                "description": "从公海领取线索的权限"
            },
            {
                "name": "退回线索",
                "code": "lead:return",
                "resource": "lead",
                "action": "return",
                "scope": None,
                "description": "将线索退回公海的权限"
            },
            {
                "name": "转化线索",
                "code": "lead:convert",
                "resource": "lead",
                "action": "convert",
                "scope": None,
                "description": "将线索转化为客户的权限"
            },
            {
                "name": "添加跟进记录",
                "code": "lead:followup",
                "resource": "lead",
                "action": "followup",
                "scope": None,
                "description": "添加线索跟进记录的权限"
            },
            {
                "name": "管理用户",
                "code": "user:manage",
                "resource": "user",
                "action": "manage",
                "scope": None,
                "description": "管理用户的权限"
            },
            {
                "name": "管理角色",
                "code": "role:manage",
                "resource": "role",
                "action": "manage",
                "scope": None,
                "description": "管理角色的权限"
            },
            {
                "name": "管理权限",
                "code": "permission:manage",
                "resource": "permission",
                "action": "manage",
                "scope": None,
                "description": "管理权限的权限"
            },
            {
                "name": "系统配置",
                "code": "system:config",
                "resource": "system",
                "action": "config",
                "scope": None,
                "description": "系统配置的权限"
            }
        ]

        created_permissions = {}
        for perm_data in permissions_data:
            permission = permission_crud.create(db, PermissionCreate(**perm_data))
            created_permissions[permission.code] = permission
            print(f"创建权限: {permission.name}")

        role_permissions_mapping = {
            "SALES_DIRECTOR": [
                "customer:view:all",
                "customer:create",
                "customer:update",
                "customer:delete",
                "customer:convert",
                "customer:status",
                "contact:manage",
                "customer:followup:create",
                "customer:followup:view",
                "customer:followup:delete",
                "opportunity:view:all",
                "opportunity:create",
                "opportunity:update",
                "opportunity:delete",
                "opportunity:stage",
                "opportunity:win",
                "opportunity:lose",
                "opportunity:stage:manage",
                "opportunity:analytics:view",
                "report:view:team",
                "lead:view:all",
                "lead:create",
                "lead:update",
                "lead:delete",
                "lead:assign",
                "lead:claim",
                "lead:return",
                "lead:convert",
                "lead:followup"
            ],
            "SALES_MEMBER": [
                "customer:view:own",
                "customer:create",
                "customer:update",
                "customer:convert",
                "customer:status",
                "contact:manage",
                "customer:followup:create",
                "customer:followup:view",
                "customer:followup:delete",
                "opportunity:view:own",
                "opportunity:create",
                "opportunity:update",
                "opportunity:stage",
                "opportunity:win",
                "opportunity:lose",
                "opportunity:analytics:view",
                "lead:view:own",
                "lead:create",
                "lead:update",
                "lead:claim",
                "lead:return",
                "lead:convert",
                "lead:followup"
            ],
            "SYSTEM_ADMIN": [
                "user:manage",
                "role:manage",
                "permission:manage",
                "system:config",
                "customer:view:all",
                "customer:create",
                "customer:update",
                "customer:delete",
                "customer:convert",
                "customer:status",
                "contact:manage",
                "customer:followup:create",
                "customer:followup:view",
                "customer:followup:delete",
                "opportunity:view:all",
                "opportunity:create",
                "opportunity:update",
                "opportunity:delete",
                "opportunity:stage",
                "opportunity:win",
                "opportunity:lose",
                "opportunity:stage:manage",
                "opportunity:analytics:view",
                "lead:view:all",
                "lead:create",
                "lead:update",
                "lead:delete",
                "lead:assign",
                "lead:claim",
                "lead:return",
                "lead:convert",
                "lead:followup"
            ]
        }

        for role_code, permission_codes in role_permissions_mapping.items():
            role = created_roles[role_code]
            for perm_code in permission_codes:
                permission = created_permissions[perm_code]
                permission_crud.assign_to_role(db, role.id, permission.id)
                print(f"为角色 {role.name} 分配权限: {permission.name}")

        print("角色和权限初始化完成")

    except Exception as e:
        print(f"初始化失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("开始初始化数据库...")
    init_database()
    init_roles_and_permissions()
    print("数据库初始化完成!")
