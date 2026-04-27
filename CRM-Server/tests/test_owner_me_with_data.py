import requests
from app.core.database import get_db
from sqlalchemy import text

BASE_URL = "http://localhost:8000"

def create_sales_director():
    """创建销售总监用户"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "测试用户",
            "email": "testuser@example.com",
            "region": "北京"
        }
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token"), data.get("user", {}).get("feishu_open_id")
    return None, None

def get_all_customers(token):
    """获取所有客户"""
    response = requests.get(
        f"{BASE_URL}/api/v1/customers/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def assign_customer_in_db(customer_id, new_owner_id):
    """直接在数据库中分配客户"""
    db = next(get_db())
    try:
        db.execute(
            text("UPDATE crm_customers SET owner_id = :owner_id WHERE id = :customer_id"),
            {"owner_id": new_owner_id, "customer_id": customer_id}
        )
        db.commit()
        print(f"✅ 数据库更新成功：客户 {customer_id} 已分配给 {new_owner_id}")
        return True
    except Exception as e:
        print(f"❌ 数据库更新失败：{e}")
        return False
    finally:
        db.close()

def test_owner_id_me(token):
    """测试 owner_id=me 参数"""
    print("\n=== 测试：owner_id=me 参数 ===")
    
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
                print(f"  - {customer['account_name']} (ID: {customer['id']}, 负责人ID: {customer.get('owner_id')})")
        
        return customers
    else:
        print(f"❌ 请求失败: {response.text}")
        return None

def main():
    print("=" * 60)
    print("owner_id=me 功能完整测试")
    print("=" * 60)
    
    print("\n1. 创建销售总监用户...")
    token, feishu_open_id = create_sales_director()
    if not token:
        print("❌ 创建用户失败")
        return
    
    print(f"✅ 用户创建成功")
    print(f"   feishu_open_id: {feishu_open_id}")
    
    print("\n2. 获取所有客户...")
    customers = get_all_customers(token)
    if not customers or len(customers) == 0:
        print("❌ 没有找到客户")
        return
    
    print(f"✅ 找到 {len(customers)} 个客户")
    test_customer = customers[0]
    customer_id = test_customer['id']
    print(f"   选择客户: {test_customer['account_name']} (ID: {customer_id})")
    print(f"   当前负责人: {test_customer.get('owner_id') or '无'}")
    
    print("\n3. 测试 owner_id=me（分配前）...")
    customers_me = test_owner_id_me(token)
    
    print(f"\n4. 将客户 {customer_id} 分配给当前用户 {feishu_open_id}...")
    if assign_customer_in_db(customer_id, feishu_open_id):
        print("✅ 分配成功")
    
    print("\n5. 测试 owner_id=me（分配后）...")
    customers_me_after = test_owner_id_me(token)
    
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    if customers_me is not None and customers_me_after is not None:
        print(f"\n分配前使用 owner_id=me: 找到 {len(customers_me)} 个客户")
        print(f"分配后使用 owner_id=me: 找到 {len(customers_me_after)} 个客户")
        
        if len(customers_me_after) > len(customers_me):
            print("\n✅✅✅ owner_id=me 功能完全正常！")
            print("   后端正确将 'me' 替换为当前用户的 feishu_open_id")
            print("   数据库正确返回属于当前用户的客户")
        elif len(customers_me_after) == len(customers_me):
            print("\n⚠️  客户数量没有变化，请检查数据库")
        else:
            print("\n❌ 出现异常，客户数量减少了")

if __name__ == "__main__":
    main()
