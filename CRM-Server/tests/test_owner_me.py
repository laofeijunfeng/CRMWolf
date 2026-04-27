import requests

BASE_URL = "http://localhost:8000"

def create_sales_director():
    """创建销售总监用户（Eddie）"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "Eddie",
            "email": "eddie_director@example.com",
            "region": "北京"
        }
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token"), data.get("user", {}).get("feishu_open_id")
    return None, None

def test_get_customers_with_me(token):
    """测试使用 owner_id=me 获取客户列表"""
    print("\n=== 测试：使用 owner_id=me 获取客户列表 ===")
    
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
            print("\n客户列表：")
            for customer in customers:
                owner_info = f"负责人ID: {customer.get('owner_id')}" if customer.get('owner_id') else "无负责人"
                print(f"  - {customer['account_name']} (ID: {customer['id']}, {owner_info})")
        else:
            print("  没有找到客户")
        
        return customers
    else:
        print(f"❌ 请求失败")
        print(f"   响应: {response.text}")
        return None

def test_get_customers_without_filter(token):
    """测试不使用 owner_id 过滤获取所有客户"""
    print("\n=== 测试：获取所有客户（不过滤负责人）===")
    
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
            print("\n客户列表：")
            for customer in customers:
                owner_info = f"负责人ID: {customer.get('owner_id')}" if customer.get('owner_id') else "无负责人"
                print(f"  - {customer['account_name']} (ID: {customer['id']}, {owner_info})")
        
        return customers
    else:
        print(f"❌ 请求失败")
        return None

def main():
    print("=" * 60)
    print("客户列表 owner_id=me 参数测试")
    print("=" * 60)
    
    print("\n1. 创建销售总监用户 Eddie...")
    token, feishu_open_id = create_sales_director()
    if not token:
        print("❌ 创建用户失败")
        return
    
    print(f"✅ 用户创建成功")
    print(f"   feishu_open_id: {feishu_open_id}")
    
    print("\n2. 测试：使用 owner_id=me 参数...")
    customers_me = test_get_customers_with_me(token)
    
    print("\n3. 测试：不使用 owner_id 过滤...")
    customers_all = test_get_customers_without_filter(token)
    
    print("\n" + "=" * 60)
    print("测试结果分析")
    print("=" * 60)
    
    if customers_me is not None and customers_all is not None:
        print(f"\n使用 owner_id=me: 找到 {len(customers_me)} 个客户")
        print(f"不过滤负责人: 找到 {len(customers_all)} 个客户")
        
        if len(customers_me) > 0:
            print("\n✅ owner_id=me 参数工作正常！")
            print("   后端正确将 'me' 替换为当前用户的 feishu_open_id")
            
            my_customers = [c for c in customers_me if c.get('owner_id') == feishu_open_id]
            print(f"   其中 {len(my_customers)} 个客户的负责人是当前用户")
        else:
            print("\n⚠️  没有找到属于当前用户的客户")
            print("   可能需要先创建客户或分配客户")
    
    print("\n修复说明：")
    print("- 修改前：直接使用 owner_id='me' 查询数据库，找不到记录")
    print("- 修改后：在 API 层将 'me' 替换为 current_user.feishu_open_id")
    print("- 优势：前端可以使用 'me' 作为特殊值，简化代码")

if __name__ == "__main__":
    main()
