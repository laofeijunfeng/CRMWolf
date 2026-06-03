"""
权限问题调试脚本

在服务器上运行，排查用户权限问题：
python3 scripts/debug_permissions.py <user_id>

例如：
python3 scripts/debug_permissions.py 2
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user import User
from app.models.team import Team, UserTeam
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.crud.permission import permission_crud
from app.services.permission_service import permission_service


def debug_user_permissions(user_id: int):
    """调试用户权限"""
    db = SessionLocal()
    try:
        print(f"\n{'='*60}")
        print(f"权限调试 - 用户 ID: {user_id}")
        print(f"{'='*60}\n")

        # 1. 用户基本信息
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"❌ 用户不存在")
            return
        print(f"✓ 用户: {user.name} ({user.email})")

        # 2. 检查团队关系
        print(f"\n--- 团队关系 ---")
        user_teams = db.query(UserTeam).filter(UserTeam.user_id == user_id).all()
        if not user_teams:
            print(f"❌ 用户没有加入任何团队")
            return

        current_team_id = None
        for ut in user_teams:
            status = "当前活跃" if ut.current_team else "非活跃"
            team = db.query(Team).filter(Team.id == ut.team_id).first()
            print(f"  团队 {ut.team_id} ({team.name if team else '?'}): {status}")
            if ut.current_team:
                current_team_id = ut.team_id

        if not current_team_id:
            print(f"❌ 用户没有活跃团队（current_team 都为 False）")
            # 尝试修复：设置第一个团队为活跃
            first_team = user_teams[0]
            first_team.current_team = True
            db.commit()
            current_team_id = first_team.team_id
            print(f"  → 已修复：设置团队 {current_team_id} 为活跃")

        # 3. 检查角色分配
        print(f"\n--- 角色分配 (team_id={current_team_id}) ---")
        user_roles = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.team_id == current_team_id
        ).all()

        if not user_roles:
            print(f"❌ 用户在该团队没有角色")

            # 检查是否是团队创建者
            team = db.query(Team).filter(Team.id == current_team_id).first()
            if team and team.owner_id == user_id:
                print(f"  用户是团队创建者，需要分配 TEAM_ADMIN 角色")
                team_admin = db.query(Role).filter(Role.code == "TEAM_ADMIN").first()
                if team_admin:
                    ur = UserRole(user_id=user_id, role_id=team_admin.id, team_id=current_team_id)
                    db.add(ur)
                    db.commit()
                    print(f"  → 已修复：分配 TEAM_ADMIN 角色")

                    # 清除缓存
                    permission_service.clear_user_permissions_cache(user_id, current_team_id)
                    print(f"  → 已清除权限缓存")

                    user_roles = db.query(UserRole).filter(
                        UserRole.user_id == user_id,
                        UserRole.team_id == current_team_id
                    ).all()

        for ur in user_roles:
            role = db.query(Role).filter(Role.id == ur.role_id).first()
            print(f"  ✓ 角色: {role.code} ({role.name})")

        # 4. 检查角色权限
        print(f"\n--- 角色权限 ---")
        for ur in user_roles:
            role = db.query(Role).filter(Role.id == ur.role_id).first()
            rp_count = db.query(RolePermission).filter(
                RolePermission.role_id == ur.role_id
            ).count()
            print(f"  {role.code}: {rp_count} 个权限")

            if rp_count == 0:
                print(f"  ❌ 该角色没有权限关联")
                # 需要运行迁移脚本

        # 5. 获取用户实际权限
        print(f"\n--- 用户实际权限 ---")
        perms = permission_crud.get_user_permissions(db, user_id, current_team_id)
        print(f"  权限总数: {len(perms)}")

        if perms:
            # 显示关键管理权限
            key_perms = ['user:manage', 'role:manage', 'permission:manage', 'system:config']
            print(f"  关键管理权限:")
            for kp in key_perms:
                has = any(p.code == kp for p in perms)
                print(f"    {'✓' if has else '❌'} {kp}")

            print(f"  前 10 个权限:")
            for p in perms[:10]:
                print(f"    {p.code}")
        else:
            print(f"  ❌ 用户没有任何权限")

        # 6. 清除缓存测试
        print(f"\n--- 缓存清除测试 ---")
        success = permission_service.clear_user_permissions_cache(user_id, current_team_id)
        print(f"  {'✓' if success else '❌'} 缓存清除")

        # 7. 重新获取权限（不使用缓存）
        print(f"\n--- 重新获取权限（无缓存）---")
        perms2, cached = permission_service.get_user_permissions_with_cache(
            db, user_id, current_team_id, use_cache=False
        )
        print(f"  权限总数: {len(perms2)}, 来自缓存: {cached}")

        print(f"\n{'='*60}")
        print("调试完成")
        print(f"{'='*60}\n")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 scripts/debug_permissions.py <user_id>")
        print("例如: python3 scripts/debug_permissions.py 2")
        sys.exit(1)

    user_id = int(sys.argv[1])
    debug_user_permissions(user_id)