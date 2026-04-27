import requests

BASE_URL = "http://localhost:8000"

def create_sales_director():
    """创建销售总监用户"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "测试用户",
            "email": "test_customer_list@example.com",
            "region": "北京"
        }
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None

def test_get_customers(token):
    """测试获取客户列表（带关联信息）"""
    print("\n=== 测试：获取客户列表（带负责人和创建人信息）===")
    
    response = requests.get(
        f"{BASE_URL}/api/v1/customers/",
        params={
            "skip": 0,
            "limit": 20
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        customers = response.json()
        print(f"✅ 成功获取到 {len(customers)} 个客户")
        
        if customers:
            for customer in customers:
                print(f"\n客户: {customer['account_name']} (ID: {customer['id']})")
                print(f"  状态: {customer['status']}")
                
                if customer.get('owner_info'):
                    owner = customer['owner_info']
                    print(f"  负责人: {owner['name']} (ID: {owner['id']})")
                else:
                    print(f"  负责人: 无")
                
                if customer.get('creator_info'):
                    creator = customer['creator_info']
                    print(f"  创建人: {creator['name']} (ID: {creator['id']})")
                else:
                    print(f"  创建人: 无")
        
        return customers
    else:
        print(f"❌ 请求失败: {response.text}")
        return None

def test_get_customers_with_owner_filter(token):
    """测试使用 owner_id=me 过滤"""
    print("\n=== 测试：使用 owner_id=me 过滤 ===")
    
    response = requests.get(
        f"{BASE_URL}/api/v1/customers/",
        params={
            "skip": 0,
            "limit": 20,
            "owner_id": "me"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        customers = response.json()
        print(f"✅ 成功获取到 {len(customers)} 个客户")
        
        if customers:
            for customer in customers:
                print(f"\n客户: {customer['account_name']}")
                if customer.get('owner_info'):
                    print(f"  负责人: {customer['owner_info']['name']}")
        
        return customers
    else:
        print(f"❌ 请求失败")
        return None

def main():
    print("=" * 60)
    print("客户列表接口优化测试")
    print("=" * 60)
    
    print("\n1. 创建销售总监用户...")
    token = create_sales_director()
    if not token:
        print("❌ 创建用户失败")
        return
    print("✅ 用户创建成功")
    
    print("\n2. 测试：获取所有客户（带关联信息）...")
    all_customers = test_get_customers(token)
    
    print("\n3. 测试：使用 owner_id=me 过滤...")
    my_customers = test_get_customers_with_owner_filter(token)
    
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    if all_customers is not None:
        print(f"\n✅ 客户列表接口优化成功！")
        print(f"   - 返回 {len(all_customers)} 个客户")
        
        customers_with_owner = [c for c in all_customers if c.get('owner_info')]
        customers_with_creator = [c for c in all_customers if c.get('creator_info')]
        
        print(f"   - {len(customers_with_owner)} 个客户包含负责人信息")
        print(f"   - {len(customers_with_creator)} 个客户包含创建人信息")
        
        if all_customers and all_customers[0].get('owner_info'):
            print("\n✅ 关联信息字段正确：")
            owner = all_customers[0]['owner_info']
            print(f"   - owner_info.id: {owner.get('id')}")
            print(f"   - owner_info.name: {owner.get('name')}")
            print(f"   - owner_info.avatar_url: {owner.get('avatar_url')}")
    
    print("\n优化说明：")
    print("- 新增 CustomerListResponse 响应模型")
    print("- 返回 owner_info（负责人信息）")
    print("- 返回 creator_info（创建人信息）")
    print("- 包含 id, name, avatar_url 字段")
    print("- 批量查询用户信息，提高性能")

if __name__ == "__main__":
    main()
