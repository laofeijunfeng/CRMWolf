"""
测试用户列表接口（包含角色信息）
"""
import requests


def test_users_with_roles():
    base_url = "http://localhost:8000/api/v1"
    
    print("=" * 80)
    print("测试用户列表接口（包含角色信息）")
    print("=" * 80)
    
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    print("\n1. 登录获取token...")
    response = requests.post(f"{base_url}/auth/login", json=login_data)
    
    if response.status_code != 200:
        print(f"登录失败: {response.status_code}")
        print(response.text)
        return
    
    token = response.json()["access_token"]
    print("✓ 登录成功")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    print("\n2. 获取用户列表...")
    response = requests.get(f"{base_url}/users/", headers=headers)
    
    if response.status_code != 200:
        print(f"获取用户列表失败: {response.status_code}")
        print(response.text)
        return
    
    users = response.json()
    print(f"✓ 成功获取 {len(users)} 个用户")
    
    print("\n用户列表（包含角色）:")
    for user in users:
        print(f"\n用户: {user['name']} (ID: {user['id']})")
        print(f"  邮箱: {user.get('email', 'N/A')}")
        print(f"  地区: {user.get('region', 'N/A')}")
        print(f"  状态: {user['status']}")
        
        if user.get('roles'):
            print(f"  角色:")
            for role in user['roles']:
                print(f"    - {role['name']} ({role['code']})")
        else:
            print(f"  角色: 无")
    
    print("\n" + "=" * 80)
    print("3. 测试用户详情接口...")
    if users:
        first_user_id = users[0]['id']
        response = requests.get(f"{base_url}/users/{first_user_id}", headers=headers)
        
        if response.status_code == 200:
            user_detail = response.json()
            print(f"✓ 成功获取用户详情: {user_detail['name']}")
            
            if user_detail.get('roles'):
                print(f"  用户角色:")
                for role in user_detail['roles']:
                    print(f"    - {role['name']} ({role['code']})")
        else:
            print(f"获取用户详情失败: {response.status_code}")
            print(response.text)
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    test_users_with_roles()
