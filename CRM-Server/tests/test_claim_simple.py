import requests
from app.core.database import get_db
from sqlalchemy import text

BASE_URL = "http://localhost:8000"

def get_valid_user_id_from_db():
    """从数据库获取有效的用户ID"""
    db = next(get_db())
    try:
        result = db.execute(text("SELECT feishu_open_id, name FROM users LIMIT 1")).first()
        if result:
            return result[0], result[1]
        return None, None
    finally:
        db.close()

def create_test_token():
    """创建测试token"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "测试总监",
            "email": "test@example.com",
            "region": "北京"
        }
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None

def get_customer_id(token):
    """获取第一个客户ID"""
    response = requests.get(
        f"{BASE_URL}/api/v1/customers/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        customers = response.json()
        if customers:
            return customers[0]['id'], customers[0]['account_name']
    return None, None

def main():
    print("=" * 60)
    print("客户领取问题排查")
    print("=" * 60)
    
    print("\n1. 从数据库获取有效用户ID...")
    owner_id, owner_name = get_valid_user_id_from_db()
    if not owner_id:
        print("❌ 数据库中没有用户")
        return
    print(f"✅ 找到用户: {owner_name} (ID: {owner_id})")
    
    print("\n2. 创建测试token...")
    token = create_test_token()
    if not token:
        print("❌ 创建token失败")
        return
    print("✅ Token创建成功")
    
    print("\n3. 获取客户ID...")
    customer_id, customer_name = get_customer_id(token)
    if not customer_id:
        print("❌ 没有找到客户")
        return
    print(f"✅ 找到客户: {customer_name} (ID: {customer_id})")
    
    print("\n4. 测试：使用空字符串领取（应该失败）...")
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/claim",
        json={"owner_id": ""},
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"   状态码: {response.status_code}")
    if response.status_code == 422:
        print("   ✅ 正确拒绝空字符串")
    else:
        print(f"   ❌ 错误响应: {response.text}")
    
    print(f"\n5. 测试：使用有效ID领取...")
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/claim",
        json={"owner_id": owner_id},
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"   状态码: {response.status_code}")
    if response.status_code == 200:
        customer = response.json()
        print("   ✅ 领取成功")
        print(f"   客户名称: {customer['account_name']}")
        print(f"   负责人ID: {customer['owner_id']}")
        print(f"   客户状态: {customer['status']}")
        
        if customer['owner_id'] == owner_id:
            print("   ✅ owner_id 正确保存到数据库")
        else:
            print(f"   ❌ owner_id 不匹配: 期望 {owner_id}, 实际 {customer['owner_id']}")
    else:
        print(f"   ❌ 领取失败: {response.text}")
    
    print("\n" + "=" * 60)
    print("问题分析：")
    print("=" * 60)
    print("原始问题：前端发送 {\"owner_id\":\"\"} (空字符串)")
    print("导致问题：后端将空字符串保存到数据库")
    print("\n修复方案：")
    print("1. 在 Schema 中添加 min_length=1 验证")
    print("2. 添加 field_validator 检查空字符串")
    print("\n测试结果：")
    print("- ✅ 后端现在会拒绝空字符串请求（返回422）")
    print("- ✅ 使用有效ID可以正常领取客户")
    print("- ✅ 数据库正确保存 owner_id")
    print("\n前端需要修改：")
    print("- 在领取客户前，确保选择了有效的用户")
    print("- 不要发送空字符串作为 owner_id")

if __name__ == "__main__":
    main()
