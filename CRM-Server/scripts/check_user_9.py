"""
检查用户ID=9的权限配置
"""
from app.core.database import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from sqlalchemy import text


def check_user_permissions():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("检查用户ID=9的权限配置")
        print("=" * 60)
        
        user = db.query(User).filter(User.id == 9).first()
        if not user:
            print("\n用户ID=9 不存在")
            return
        
        print(f"\n用户信息:")
        print(f"  ID: {user.id}")
        print(f"  姓名: {user.name}")
        print(f"  飞书Open ID: {user.feishu_open_id}")
        
        print(f"\n用户角色:")
        user_roles_query = """
            SELECT r.id, r.name, r.code
            FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = 9
        """
        user_roles = db.execute(text(user_roles_query)).fetchall()
        
        if user_roles:
            for role_id, role_name, role_code in user_roles:
                print(f"  - {role_name} ({role_code})")
                
                perms_query = """
                    SELECT p.name, p.code
                    FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    WHERE rp.role_id = :role_id
                """
                role_perms = db.execute(text(perms_query), {"role_id": role_id}).fetchall()
                
                print(f"\n角色 '{role_name}' 的所有权限:")
                for perm_name, perm_code in role_perms:
                    status = "✓" if perm_code == "opportunity:create" else " "
                    print(f"    {status} {perm_name} ({perm_code})")
        else:
            print("  用户未分配任何角色")
        
        print(f"\n商机相关权限检查:")
        if user_roles:
            all_perms = set()
            for role_id, role_name, role_code in user_roles:
                perms_query = """
                    SELECT p.code
                    FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    WHERE rp.role_id = :role_id
                """
                role_perms = db.execute(text(perms_query), {"role_id": role_id}).fetchall()
                for (perm_code,) in role_perms:
                    all_perms.add(perm_code)
            
            if "opportunity:create" in all_perms:
                print(f"  ✓ 用户具有 'opportunity:create' 权限")
            else:
                print(f"  ✗ 用户不具有 'opportunity:create' 权限")
                print(f"\n  用户当前所有权限代码:")
                for perm_code in sorted(all_perms):
                    print(f"    - {perm_code}")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"查询失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_user_permissions()
