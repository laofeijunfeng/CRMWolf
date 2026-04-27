"""
测试用户API是否返回角色信息
"""
import json


def simulate_api_response():
    """模拟API响应来验证数据结构"""
    
    print("=" * 80)
    print("模拟用户API响应结构验证")
    print("=" * 80)
    
    from app.core.database import SessionLocal
    from sqlalchemy import text
    from app.schemas.user import UserWithRolesResponse
    
    db = SessionLocal()
    try:
        users_query = """
            SELECT u.id, u.name, u.en_name, u.email, u.mobile, u.avatar_url, 
                   u.employee_no, u.region, u.feishu_open_id, u.feishu_union_id,
                   u.feishu_user_id, u.tenant_key, u.status, u.created_at, u.updated_at
            FROM users u
            ORDER BY u.id
            LIMIT 3
        """
        users = db.execute(text(users_query)).fetchall()
        
        print(f"\n1. 处理 {len(users)} 个用户的API响应...")
        
        for user in users:
            user_id = user[0]
            
            roles_query = """
                SELECT r.id, r.name, r.code
                FROM roles r
                JOIN user_roles ur ON r.id = ur.role_id
                WHERE ur.user_id = :user_id
                GROUP BY r.id, r.name, r.code
            """
            roles = db.execute(text(roles_query), {"user_id": user_id}).fetchall()
            
            role_list = [{"id": r[0], "name": r[1], "code": r[2]} for r in roles]
            
            user_dict = {
                "id": user[0],
                "name": user[1],
                "en_name": user[2],
                "email": user[3],
                "mobile": user[4],
                "avatar_url": user[5],
                "employee_no": user[6],
                "region": user[7],
                "feishu_open_id": user[8],
                "feishu_union_id": user[9],
                "feishu_user_id": user[10],
                "tenant_key": user[11],
                "status": str(user[12]).lower() if user[12] else None,
                "created_at": user[13].isoformat() if user[13] else None,
                "updated_at": user[14].isoformat() if user[14] else None,
                "roles": role_list
            }
            
            print(f"\n用户: {user_dict['name']} (ID: {user_dict['id']})")
            print(f"  邮箱: {user_dict.get('email', 'N/A')}")
            print(f"  状态: {user_dict['status']}")
            
            if user_dict.get('roles'):
                print(f"  角色数量: {len(user_dict['roles'])}")
                for role in user_dict['roles'][:3]:
                    print(f"    - {role['name']} ({role['code']})")
                if len(user_dict['roles']) > 3:
                    print(f"    ... 还有 {len(user_dict['roles']) - 3} 个角色")
            else:
                print(f"  角色: 无")
            
            try:
                validated = UserWithRolesResponse(**user_dict)
                print(f"  ✓ Schema验证通过")
            except Exception as e:
                print(f"  ✗ Schema验证失败: {e}")
        
        print("\n" + "=" * 80)
        print("API响应结构验证完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n操作失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    simulate_api_response()
