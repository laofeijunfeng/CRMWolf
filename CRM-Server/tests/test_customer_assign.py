import requests
from datetime import date

BASE_URL = "http://localhost:8000"

def create_sales_director():
    """创建销售总监用户"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "销售总监",
            "email": "director_assign@example.com",
            "region": "北京"
        }
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    return None

def get_all_customers(token):
    """获取所有客户"""
    response = requests.get(
        f"{BASE_URL}/api/v1/customers/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def get_user_list(token):
    """获取用户列表"""
    response = requests.get(
        f"{BASE_URL}/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def test_assign_customer(token, customer_id, new_owner_id):
    """测试分配客户"""
    print(f"\n=== 测试分配客户 {customer_id} 给用户 {new_owner_id} ===")
    
    assign_data = {
        "owner_id": new_owner_id,
        "remark": "测试分配功能"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/assign",
        json=assign_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        customer = response.json()
        print("✅ 客户分配成功！")
        print(f"   客户ID: {customer['id']}")
        print(f"   客户名称: {customer['account_name']}")
        print(f"   新负责人ID: {customer['owner_id']}")
        print(f"   客户状态: {customer['status']}")
        return customer
    else:
        print(f"❌ 分配客户失败: {response.status_code}")
        print(response.text)
        return None

def test_assign_with_regular_user(customer_id, new_owner_id, user_token):
    """测试普通用户尝试分配客户（应该失败）"""
    print(f"\n=== 测试普通用户尝试分配客户（应该失败）===")
    
    assign_data = {
        "owner_id": new_owner_id
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/assign",
        json=assign_data,
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    if response.status_code == 403:
        print("✅ 权限检查正常：普通用户无法分配客户")
        return True
    else:
        print(f"❌ 权限检查异常：返回状态码 {response.status_code}")
        return False

def main():
    print("=" * 50)
    print("客户分配功能测试")
    print("=" * 50)
    
    print("\n1. 创建销售总监用户...")
    director_token = create_sales_director()
    if not director_token:
        print("❌ 创建销售总监失败")
        return
    print("✅ 销售总监创建成功")
    
    print("\n2. 获取客户列表...")
    customers = get_all_customers(director_token)
    if not customers or len(customers) == 0:
        print("❌ 没有找到客户，请先创建客户")
        return
    
    print(f"✅ 找到 {len(customers)} 个客户")
    
    print("\n3. 获取用户列表...")
    users = get_user_list(director_token)
    if not users or len(users) < 2:
        print("❌ 用户数量不足，无法测试分配功能")
        return
    
    print(f"✅ 找到 {len(users)} 个用户")
    
    test_customer = customers[0]
    test_customer_id = test_customer['id']
    original_owner = test_customer.get('owner_id')
    
    print(f"\n选择测试客户: {test_customer['account_name']} (ID: {test_customer_id})")
    print(f"当前负责人: {original_owner if original_owner else '无'}")
    
    target_user = users[0]
    target_owner_id = target_user['feishu_open_id']
    print(f"目标用户: {target_user['name']} (ID: {target_owner_id})")
    
    result = test_assign_customer(director_token, test_customer_id, target_owner_id)
    
    if result:
        print(f"\n✅ 分配后客户信息:")
        print(f"   负责人ID: {result['owner_id']}")
        print(f"   客户状态: {result['status']} (0=跟进中)")
        
        if result['owner_id'] == target_owner_id:
            print("✅ 分配成功：负责人已更新")
        else:
            print("❌ 分配失败：负责人未更新")
    
    print("\n" + "=" * 50)
    print("✅ 测试完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()
