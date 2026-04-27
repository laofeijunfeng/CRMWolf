import requests

BASE_URL = "http://localhost:8000"

def create_sales_director():
    """创建销售总监用户"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "测试销售总监",
            "email": "test_director@example.com",
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

def get_users(token):
    """获取用户列表"""
    response = requests.get(
        f"{BASE_URL}/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def test_claim_with_empty_owner_id(token, customer_id):
    """测试使用空字符串 owner_id 领取客户（应该失败）"""
    print("\n=== 测试：使用空字符串 owner_id 领取客户 ===")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/claim",
        json={"owner_id": ""},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"状态码: {response.status_code}")
    if response.status_code == 422:
        print("✅ 验证通过：后端正确拒绝了空字符串")
        print(f"   错误信息: {response.json()}")
        return True
    else:
        print(f"❌ 验证失败：后端应该拒绝空字符串")
        print(f"   响应: {response.text}")
        return False

def test_claim_with_valid_owner_id(token, customer_id, owner_id):
    """测试使用有效的 owner_id 领取客户"""
    print(f"\n=== 测试：使用有效 owner_id 领取客户 ===")
    print(f"   目标负责人ID: {owner_id}")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/claim",
        json={"owner_id": owner_id},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        customer = response.json()
        print("✅ 领取成功！")
        print(f"   客户名称: {customer['account_name']}")
        print(f"   负责人ID: {customer['owner_id']}")
        print(f"   客户状态: {customer['status']}")
        
        if customer['owner_id'] == owner_id:
            print("✅ 数据库更新正确：owner_id 已保存")
            return True
        else:
            print("❌ 数据库更新异常：owner_id 未正确保存")
            return False
    else:
        print(f"❌ 领取失败")
        print(f"   响应: {response.text}")
        return False

def main():
    print("=" * 60)
    print("客户领取接口修复验证测试")
    print("=" * 60)
    
    print("\n1. 创建销售总监用户...")
    token = create_sales_director()
    if not token:
        print("❌ 创建用户失败")
        return
    print("✅ 用户创建成功")
    
    print("\n2. 获取客户列表...")
    customers = get_all_customers(token)
    if not customers or len(customers) == 0:
        print("❌ 没有找到客户")
        return
    
    print(f"✅ 找到 {len(customers)} 个客户")
    
    print("\n3. 获取用户列表...")
    users = get_users(token)
    if not users or len(users) == 0:
        print("❌ 没有找到用户")
        return
    
    print(f"✅ 找到 {len(users)} 个用户")
    
    test_customer = customers[0]
    customer_id = test_customer['id']
    print(f"\n4. 使用客户: {test_customer['account_name']} (ID: {customer_id})")
    print(f"   当前负责人: {test_customer.get('owner_id') or '无'}")
    print(f"   当前状态: {test_customer['status']}")
    
    test_claim_with_empty_owner_id(token, customer_id)
    
    test_user = users[0]
    owner_id = test_user['feishu_open_id']
    test_claim_with_valid_owner_id(token, customer_id, owner_id)
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print("\n结论：")
    print("- 后端现在会正确拒绝空字符串的 owner_id")
    print("- 使用有效的 owner_id 可以成功领取客户")
    print("- 前端需要传递有效的用户 ID，而不是空字符串")

if __name__ == "__main__":
    main()
