"""
直接检查数据库中的用户和角色数据
"""
from app.core.database import SessionLocal
from sqlalchemy import text


def check_users_with_roles():
    db = SessionLocal()
    try:
        print("=" * 80)
        print("检查数据库中的用户和角色数据")
        print("=" * 80)
        
        print("\n1. 所有用户及其角色:")
        users_query = """
            SELECT u.id, u.name, u.email, u.status, u.region
            FROM users u
            ORDER BY u.id
        """
        users = db.execute(text(users_query)).fetchall()
        
        for user_id, name, email, user_status, region in users:
            print(f"\n用户: {name} (ID: {user_id})")
            print(f"  邮箱: {email or 'N/A'}")
            print(f"  地区: {region or 'N/A'}")
            print(f"  状态: {user_status}")
            
            roles_query = """
                SELECT r.id, r.name, r.code
                FROM roles r
                JOIN user_roles ur ON r.id = ur.role_id
                WHERE ur.user_id = :user_id
            """
            roles = db.execute(text(roles_query), {"user_id": user_id}).fetchall()
            
            if roles:
                print(f"  角色:")
                for role_id, role_name, role_code in roles:
                    print(f"    - [{role_id}] {role_name} ({role_code})")
            else:
                print(f"  角色: 无")
        
        print("\n" + "=" * 80)
        
        print("\n2. 角色统计:")
        stats_query = """
            SELECT r.name, r.code, COUNT(ur.user_id) as user_count
            FROM roles r
            LEFT JOIN user_roles ur ON r.id = ur.role_id
            GROUP BY r.id, r.name, r.code
            ORDER BY user_count DESC
        """
        stats = db.execute(text(stats_query)).fetchall()
        
        for role_name, role_code, user_count in stats:
            print(f"  {role_name} ({role_code}): {user_count} 个用户")
        
        print("\n" + "=" * 80)
        print("检查完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n操作失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_users_with_roles()
