#!/usr/bin/env python3
"""检查系统管理员权限"""

import sys
sys.path.append('/Users/eddie/Code/CRM')

from app.core.database import SessionLocal
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission

def check_admin_permissions():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("检查系统管理员权限")
        print("=" * 60)

        # 查找系统管理员角色
        admin_role = db.query(Role).filter(Role.code == "SYSTEM_ADMIN").first()
        
        if not admin_role:
            print("\n❌ 未找到系统管理员角色（SYSTEM_ADMIN）")
            return

        print(f"\n✅ 角色名称: {admin_role.name}")
        print(f"✅ 角色编码: {admin_role.code}")
        print(f"✅ 角色描述: {admin_role.description}")

        # 查询角色权限
        permissions = db.query(Permission).join(
            RolePermission,
            Permission.id == RolePermission.permission_id
        ).filter(
            RolePermission.role_id == admin_role.id
        ).order_by(Permission.code).all()

        print(f"\n✅ 权限总数: {len(permissions)}")
        
        # 检查关键权限
        key_permissions = {
            "user:manage": "用户管理",
            "role:manage": "角色管理", 
            "permission:manage": "权限管理",
            "system:config": "系统配置"
        }
        
        print("\n" + "=" * 60)
        print("关键权限检查：")
        print("=" * 60)
        
        permission_dict = {p.code: p for p in permissions}
        
        for perm_code, perm_name in key_permissions.items():
            if perm_code in permission_dict:
                perm = permission_dict[perm_code]
                print(f"  ✅ {perm.code:30} - {perm.name}")
            else:
                print(f"  ❌ {perm_code:30} - 未分配")

        # 检查用户和角色管理相关权限
        print("\n" + "=" * 60)
        print("用户和角色管理权限详情：")
        print("=" * 60)
        
        user_role_perms = sorted(
            [p for p in permissions if p.code.startswith("user:") or p.code.startswith("role:") or p.code.startswith("permission:")],
            key=lambda x: x.code
        )
        
        if user_role_perms:
            print(f"\n找到 {len(user_role_perms)} 个用户和角色管理权限：")
            for perm in user_role_perms:
                print(f"  ✅ {perm.code:40} - {perm.name}")
        else:
            print("\n❌ 未找到用户和角色管理权限")

        # 显示所有权限
        print("\n" + "=" * 60)
        print("所有权限列表：")
        print("=" * 60)
        print(f"\n总共 {len(permissions)} 个权限：\n")
        
        for i, perm in enumerate(permissions, 1):
            prefix = "  ✅"
            print(f"{prefix} {i:3}. {perm.code:40} - {perm.name}")

    finally:
        db.close()

if __name__ == "__main__":
    check_admin_permissions()
