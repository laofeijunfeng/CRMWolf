"""
同步权限定义到数据库

用法: python scripts/sync_permissions.py [--dry-run]

选项:
  --dry-run  只显示将要执行的更改，不实际执行
"""
import sys
import os
import argparse

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.crud.permission import permission_crud
from app.crud.role import role_crud
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.constants.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS_MAPPING


def sync_permissions(dry_run=False):
    """
    同步权限定义到数据库，并为现有角色分配新权限

    步骤:
    1. 确保所有权限定义都存在于数据库
    2. 为角色分配新权限
    """
    db = SessionLocal()

    try:
        print("=" * 60)
        print("权限同步脚本")
        print("=" * 60)

        # 1. 同步权限定义
        print("\n[步骤1] 同步权限定义...")
        new_permissions = []

        for perm_data in ALL_PERMISSIONS:
            existing = db.query(Permission).filter(
                Permission.code == perm_data["code"]
            ).first()

            if not existing:
                if not dry_run:
                    new_perm = Permission(
                        name=perm_data["name"],
                        code=perm_data["code"],
                        resource=perm_data["resource"],
                        action=perm_data["action"],
                        scope=perm_data.get("scope")
                    )
                    db.add(new_perm)
                    db.flush()
                new_permissions.append(perm_data["code"])
                print(f"  ✓ 新增权限: {perm_data['code']}")

        if not new_permissions:
            print("  - 无新增权限（所有权限已存在）")

        # 2. 同步角色权限映射
        print("\n[步骤2] 同步角色权限映射...")
        added_assignments = []

        for role_code, permissions in ROLE_PERMISSIONS_MAPPING.items():
            # TEAM_ADMIN 跳过（已有所有权限）
            if permissions == "all":
                print(f"  - {role_code}: 拥有所有权限（跳过）")
                continue

            role = db.query(Role).filter(Role.code == role_code).first()
            if not role:
                print(f"  ⚠ 角色 {role_code} 不存在，跳过")
                continue

            # 获取角色当前权限
            current_perm_ids = db.query(RolePermission.permission_id).filter(
                RolePermission.role_id == role.id
            ).all()
            current_perm_ids = [p[0] for p in current_perm_ids]
            current_perm_codes = set()

            for perm_id in current_perm_ids:
                perm = db.query(Permission).filter(Permission.id == perm_id).first()
                if perm:
                    current_perm_codes.add(perm.code)

            # 添加新权限
            for perm_code in permissions:
                if perm_code in current_perm_codes:
                    continue  # 已有权限

                perm = db.query(Permission).filter(Permission.code == perm_code).first()
                if not perm:
                    print(f"    ⚠ 权限 {perm_code} 不存在（可能未在ALL_PERMISSIONS定义）")
                    continue

                if not dry_run:
                    role_perm = RolePermission(
                        role_id=role.id,
                        permission_id=perm.id
                    )
                    db.add(role_perm)

                added_assignments.append((role_code, perm_code))
                print(f"  ✓ 为 {role_code} 添加权限: {perm_code}")

        if not added_assignments:
            print("  - 无新增权限分配（角色权限已完整）")

        # 提交更改
        if not dry_run:
            db.commit()
            print("\n[完成] 权限同步成功！")
            print(f"  - 新增权限: {len(new_permissions)} 个")
            print(f"  - 新增分配: {len(added_assignments)} 个")
        else:
            print("\n[DRY RUN] 以上为预览，未实际执行")
            print("使用 python scripts/sync_permissions.py 执行实际同步")

        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"\n[错误] 同步失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="同步权限定义到数据库")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不执行")
    args = parser.parse_args()

    sync_permissions(dry_run=args.dry_run)