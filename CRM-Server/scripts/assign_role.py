"""
为用户ID=9分配销售成员角色
"""
from app.core.database import SessionLocal
from sqlalchemy import text


def assign_role():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("为用户ID=9（Eddie）分配角色")
        print("=" * 60)
        
        print("\n1. 查看所有可用角色:")
        roles = db.execute(text("SELECT id, name, code FROM roles")).fetchall()
        for role_id, role_name, role_code in roles:
            print(f"  - [{role_id}] {role_name} ({role_code})")
        
        print("\n2. 检查用户当前角色:")
        user_roles = db.execute(text(
            "SELECT r.id, r.name, r.code FROM roles r JOIN user_roles ur ON r.id = ur.role_id WHERE ur.user_id = 9"
        )).fetchall()
        
        if user_roles:
            print("  用户已有角色:")
            for role_id, role_name, role_code in user_roles:
                print(f"    - {role_name} ({role_code})")
        else:
            print("  用户当前没有角色")
        
        print("\n3. 分配销售成员角色（SALES_MEMBER）:")
        sales_member_role = db.execute(
            text("SELECT id FROM roles WHERE code = 'SALES_MEMBER'")
        ).first()
        
        if not sales_member_role:
            print("  ✗ 未找到 SALES_MEMBER 角色")
            return
        
        role_id = sales_member_role[0]
        print(f"  找到角色ID: {role_id}")
        
        print("\n4. 检查是否已存在关联:")
        existing = db.execute(
            text("SELECT * FROM user_roles WHERE user_id = 9 AND role_id = :role_id"),
            {"role_id": role_id}
        ).first()
        
        if existing:
            print("  用户已拥有此角色，无需重复分配")
            return
        
        print("\n5. 执行角色分配:")
        db.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"),
            {"user_id": 9, "role_id": role_id}
        )
        db.commit()
        
        print("  ✓ 角色分配成功！")
        
        print("\n6. 验证分配结果:")
        user_roles = db.execute(text(
            "SELECT r.id, r.name, r.code FROM roles r JOIN user_roles ur ON r.id = ur.role_id WHERE ur.user_id = 9"
        )).fetchall()
        
        print("  用户当前角色:")
        for role_id, role_name, role_code in user_roles:
            print(f"    - {role_name} ({role_code})")
        
        print("\n7. 检查角色的商机相关权限:")
        perms = db.execute(text("""
            SELECT p.name, p.code
            FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = :role_id AND p.code LIKE 'opportunity:%'
            ORDER BY p.code
        """), {"role_id": role_id}).fetchall()
        
        print("  商机相关权限:")
        for perm_name, perm_code in perms:
            print(f"    - {perm_name} ({perm_code})")
        
        print("\n" + "=" * 60)
        print("角色分配完成！用户现在可以创建商机了。")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n操作失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    assign_role()
