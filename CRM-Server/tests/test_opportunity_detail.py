import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5IiwiZXhwIjoxNzcwMzQ2Njc2fQ.EOBh48qqB6QiyOpqEqGsvlrcFpOodUiI-LHsoQCMs88"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

print("=== 测试商机详情接口 ===")
print()

response = requests.get(f"{BASE_URL}/opportunities/1", headers=headers)

print(f"状态码: {response.status_code}")
print()

if response.status_code == 200:
    data = response.json()
    print("=== 商机详情响应数据 ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print()
    
    print("=== 检查关键字段 ===")
    print(f"✓ 商机ID: {data.get('id')}")
    print(f"✓ 商机名称: {data.get('opportunity_name')}")
    print(f"✓ 客户名称: {data.get('customer_name')}")
    print(f"✓ 销售阶段: {data.get('stage', {}).get('stage_name') if data.get('stage') else 'N/A'}")
    print(f"✓ 客户信息: {'有' if data.get('customer_info') else '无'}")
    print(f"✓ 负责人信息: {'有' if data.get('owner_info') else '无'}")
    print(f"✓ 创建人信息: {'有' if data.get('creator_info') else '无'}")
    
    if data.get('customer_info'):
        customer = data['customer_info']
        print()
        print("=== 客户详细信息 ===")
        print(f"  客户ID: {customer.get('id')}")
        print(f"  公司名称: {customer.get('account_name')}")
        print(f"  所属行业: {customer.get('industry')}")
        print(f"  所在城市: {customer.get('city')}")
        print(f"  公司规模: {customer.get('company_scale')}")
        print(f"  客户状态: {customer.get('status')}")
    
    if data.get('owner_info'):
        owner = data['owner_info']
        print()
        print("=== 负责人信息 ===")
        print(f"  ID: {owner.get('id')}")
        print(f"  姓名: {owner.get('name')}")
        print(f"  头像: {owner.get('avatar_url')}")
    
    if data.get('creator_info'):
        creator = data['creator_info']
        print()
        print("=== 创建人信息 ===")
        print(f"  ID: {creator.get('id')}")
        print(f"  姓名: {creator.get('name')}")
        print(f"  头像: {creator.get('avatar_url')}")
else:
    print(f"错误: {response.text}")
