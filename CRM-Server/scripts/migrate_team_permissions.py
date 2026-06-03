"""
团队权限数据迁移脚本

用于生产环境部署后：
1. 更新角色名称（TEAM_ADMIN → 团队所有者）
2. 确保角色权限关联完整
3. 清除所有权限缓存

执行方式：
cd CRM-Server && python3 scripts/migrate_team_permissions.py
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.services.permission_service import permission_service
from app.services.init_service import ROLES_DATA, ROLE_PERMISSIONS_MAPPING


def migrate_roles(db):
    """更新角色名称和描述"""
    print("=== 步骤 1: 更新角色名称 ===")
    for role_data in ROLES_DATA:
        role = db.query(Role).filter(Role.code == role_data["code"]).first()
        if role:
            if role.name != role_data["name"]:
                role.name = role_data["name"]
                role.description = role_data["description"]
                print(f"  更新角色: {role.code} → {role.name}")
        else:
            # 创建缺失的角色
            role = Role(**role_data)
            db.add(role)
            print(f"  创建角色: {role_data['code']} - {role_data['name']}")
    db.commit()
    print("  完成")


def migrate_role_permissions(db):
    """确保角色权限关联完整"""
    print("\n=== 步骤 2: 补充角色权限 ===")
    all_permissions = db.query(Permission).all()
    all_perm_codes = {p.code for p in all_permissions}

    for role_code, perm_config in ROLE_PERMISSIONS_MAPPING.items():
        role = db.query(Role).filter(Role.code == role_code).first()
        if not role:
            print(f"  角色 {role_code} 不存在，跳过")
            continue

        # 获取当前已有的权限
        existing_perms = db.query(RolePermission.permission_id).filter(
            RolePermission.role_id == role.id
        ).all()
        existing_perm_ids = {p[0] for p in existing_perms}

        # 确定目标权限
        if perm_config == "all":
            target_perm_codes = all_perm_codes
        else:
            target_perm_codes = set(perm_config)

        target_perms = [p for p in all_permissions if p.code in target_perm_codes]

        # 添加缺失的权限
        added_count = 0
        for perm in target_perms:
            if perm.id not in existing_perm_ids:
                rp = RolePermission(role_id=role.id, permission_id=perm.id)
                db.add(rp)
                added_count += 1

        db.commit()
        print(f"  {role_code}: 添加 {added_count} 个权限")
    print("  完成")


def clear_all_caches():
    """清除所有权限缓存"""
    print("\n=== 步骤 3: 清除权限缓存 ===")
    success = permission_service.clear_all_permissions_cache()
    if success:
        print("  缓存已清除")
    else:
        print("  缓存清除失败（可能 Redis 未连接）")
    print("  完成")


def main():
    print("开始团队权限数据迁移...")
    db = SessionLocal()
    try:
        migrate_roles(db)
        migrate_role_permissions(db)
        clear_all_caches()

        # 最终验证
        print("\n=== 验证结果 ===")
        roles = db.query(Role).all()
        for r in roles:
            rp_count = db.query(RolePermission).filter(
                RolePermission.role_id == r.id
            ).count()
            print(f"  {r.code} ({r.name}): {rp_count} 个权限")

        print("\n迁移完成!")

    except Exception as e:
        print(f"\n迁移失败: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()