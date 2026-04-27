"""
初始化开放接口权限脚本
"""
from app.core.database import SessionLocal
from app.crud.permission import permission_crud
from app.crud.role import role_crud
from app.schemas.permission import PermissionCreate


def init_openapi_permissions():
    """初始化开放接口相关权限"""
    db = SessionLocal()
    try:
        print("开始初始化开放接口权限...")

        # 定义开放接口权限
        openapi_permissions = [
            # ApiKey 管理权限
            {
                "name": "管理 ApiKey",
                "code": "apikey:manage",
                "resource": "apikey",
                "action": "manage",
                "scope": None,
                "description": "创建、查看、编辑、删除 ApiKey 的权限"
            },
            # 线索开放接口权限
            {
                "name": "开放接口创建线索",
                "code": "lead:create",
                "resource": "openapi_lead",
                "action": "create",
                "scope": None,
                "description": "通过开放接口创建线索"
            },
            {
                "name": "开放接口查看线索列表",
                "code": "lead:list",
                "resource": "openapi_lead",
                "action": "list",
                "scope": None,
                "description": "通过开放接口查看线索列表"
            },
            {
                "name": "开放接口查看线索详情",
                "code": "lead:read",
                "resource": "openapi_lead",
                "action": "read",
                "scope": None,
                "description": "通过开放接口查看线索详情"
            },
            {
                "name": "开放接口转化线索",
                "code": "lead:convert",
                "resource": "openapi_lead",
                "action": "convert",
                "scope": None,
                "description": "通过开放接口转化线索"
            },
            # 客户开放接口权限
            {
                "name": "开放接口查看客户列表",
                "code": "customer:list",
                "resource": "openapi_customer",
                "action": "list",
                "scope": None,
                "description": "通过开放接口查看客户列表"
            },
            {
                "name": "开放接口查看客户详情",
                "code": "customer:read",
                "resource": "openapi_customer",
                "action": "read",
                "scope": None,
                "description": "通过开放接口查看客户详情"
            },
            {
                "name": "开放接口更新客户状态",
                "code": "customer:update",
                "resource": "openapi_customer",
                "action": "update",
                "scope": None,
                "description": "通过开放接口更新客户状态"
            },
            # 商机开放接口权限
            {
                "name": "开放接口创建商机",
                "code": "opportunity:create",
                "resource": "openapi_opportunity",
                "action": "create",
                "scope": None,
                "description": "通过开放接口创建商机"
            },
            {
                "name": "开放接口查看商机列表",
                "code": "opportunity:list",
                "resource": "openapi_opportunity",
                "action": "list",
                "scope": None,
                "description": "通过开放接口查看商机列表"
            },
            {
                "name": "开放接口查看商机详情",
                "code": "opportunity:read",
                "resource": "openapi_opportunity",
                "action": "read",
                "scope": None,
                "description": "通过开放接口查看商机详情"
            },
            {
                "name": "开放接口标记商机赢单",
                "code": "opportunity:win",
                "resource": "openapi_opportunity",
                "action": "win",
                "scope": None,
                "description": "通过开放接口标记商机赢单"
            },
            {
                "name": "开放接口标记商机输单",
                "code": "opportunity:lose",
                "resource": "openapi_opportunity",
                "action": "lose",
                "scope": None,
                "description": "通过开放接口标记商机输单"
            },
            # 合同开放接口权限
            {
                "name": "开放接口创建合同",
                "code": "contract:create",
                "resource": "openapi_contract",
                "action": "create",
                "scope": None,
                "description": "通过开放接口创建合同"
            },
            {
                "name": "开放接口查看合同列表",
                "code": "contract:list",
                "resource": "openapi_contract",
                "action": "list",
                "scope": None,
                "description": "通过开放接口查看合同列表"
            },
            {
                "name": "开放接口查看合同详情",
                "code": "contract:read",
                "resource": "openapi_contract",
                "action": "read",
                "scope": None,
                "description": "通过开放接口查看合同详情"
            },
            # 回款开放接口权限
            {
                "name": "开放接口创建回款",
                "code": "payment:create",
                "resource": "openapi_payment",
                "action": "create",
                "scope": None,
                "description": "通过开放接口创建回款计划或登记回款"
            },
            {
                "name": "开放接口查看回款列表",
                "code": "payment:list",
                "resource": "openapi_payment",
                "action": "list",
                "scope": None,
                "description": "通过开放接口查看回款列表"
            },
            {
                "name": "开放接口查看回款详情",
                "code": "payment:read",
                "resource": "openapi_payment",
                "action": "read",
                "scope": None,
                "description": "通过开放接口查看回款详情"
            },
            # 发票开放接口权限
            {
                "name": "开放接口创建发票申请",
                "code": "invoice:create",
                "resource": "openapi_invoice",
                "action": "create",
                "scope": None,
                "description": "通过开放接口创建发票申请"
            },
            {
                "name": "开放接口查看发票列表",
                "code": "invoice:list",
                "resource": "openapi_invoice",
                "action": "list",
                "scope": None,
                "description": "通过开放接口查看发票列表"
            },
            {
                "name": "开放接口审批发票",
                "code": "invoice:approve",
                "resource": "openapi_invoice",
                "action": "approve",
                "scope": None,
                "description": "通过开放接口审批或标记发票已开具"
            }
        ]

        # 创建权限
        created_permissions = {}
        for perm_data in openapi_permissions:
            existing = permission_crud.get_by_code(db, perm_data["code"])
            if existing:
                print(f"权限 {perm_data['code']} 已存在，跳过")
                created_permissions[perm_data["code"]] = existing
            else:
                perm = permission_crud.create(db, PermissionCreate(**perm_data))
                created_permissions[perm_data["code"]] = perm
                print(f"创建权限: {perm.name} ({perm.code})")

        # 为 SYSTEM_ADMIN 角色分配所有开放接口权限
        admin_role = role_crud.get_by_code(db, "SYSTEM_ADMIN")
        if admin_role:
            permission_ids = [perm.id for perm in created_permissions.values()]
            role_crud.update_permissions(db, admin_role.id, permission_ids)
            print("已为 SYSTEM_ADMIN 角色分配所有开放接口权限")

        db.commit()
        print("开放接口权限初始化完成！")

    except Exception as e:
        print(f"初始化失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_openapi_permissions()