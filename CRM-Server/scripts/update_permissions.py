from app.core.database import SessionLocal
from app.models import Permission, Role
from app.crud.permission import permission_crud
from app.crud.role import role_crud
from app.schemas.permission import PermissionCreate
from app.schemas.role import RoleCreate


def update_opportunity_permissions():
    db = SessionLocal()
    try:
        new_permissions_data = [
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
            }
        ]
        
        created_permissions = {}
        for perm_data in new_permissions_data:
            existing_perm = db.query(Permission).filter(Permission.code == perm_data['code']).first()
            if not existing_perm:
                permission = permission_crud.create(db, PermissionCreate(**perm_data))
                created_permissions[permission.code] = permission
                print(f"创建权限: {permission.name}")
            else:
                created_permissions[perm_data['code']] = existing_perm
                print(f"权限已存在: {existing_perm.name}")
        
        opportunity_permissions = [
            "opportunity:view:all",
            "opportunity:view:own",
            "opportunity:create",
            "opportunity:update",
            "opportunity:delete",
            "opportunity:stage",
            "opportunity:win",
            "opportunity:lose",
            "opportunity:stage:manage",
            "opportunity:analytics:view"
        ]
        
        director_role = db.query(Role).filter(Role.code == "SALES_DIRECTOR").first()
        if director_role:
            for perm_code in opportunity_permissions:
                permission = created_permissions.get(perm_code)
                if permission:
                    existing = db.query(RolePermission).filter(
                        RolePermission.role_id == director_role.id,
                        RolePermission.permission_id == permission.id
                    ).first()
                    if not existing:
                        permission_crud.assign_to_role(db, director_role.id, permission.id)
                        print(f"为销售总监分配权限: {permission.name}")
        
        member_role = db.query(Role).filter(Role.code == "SALES_MEMBER").first()
        if member_role:
            member_permissions = [
                "opportunity:view:own",
                "opportunity:create",
                "opportunity:update",
                "opportunity:stage",
                "opportunity:win",
                "opportunity:lose",
                "opportunity:analytics:view"
            ]
            for perm_code in member_permissions:
                permission = created_permissions.get(perm_code)
                if permission:
                    existing = db.query(RolePermission).filter(
                        RolePermission.role_id == member_role.id,
                        RolePermission.permission_id == permission.id
                    ).first()
                    if not existing:
                        permission_crud.assign_to_role(db, member_role.id, permission.id)
                        print(f"为销售成员分配权限: {permission.name}")
        
        admin_role = db.query(Role).filter(Role.code == "SYSTEM_ADMIN").first()
        if admin_role:
            for perm_code in opportunity_permissions:
                permission = created_permissions.get(perm_code)
                if permission:
                    existing = db.query(RolePermission).filter(
                        RolePermission.role_id == admin_role.id,
                        RolePermission.permission_id == permission.id
                    ).first()
                    if not existing:
                        permission_crud.assign_to_role(db, admin_role.id, permission.id)
                        print(f"为系统管理员分配权限: {permission.name}")
        
        db.commit()
        print("商机权限更新完成！")

    except Exception as e:
        print(f"更新失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    from app.models.role_permission import RolePermission
    update_opportunity_permissions()
