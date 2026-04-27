import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

def get_auth_token():
    response = requests.post(
        "http://localhost:8000/dev/mock-login",
        json={
            "name": "AdminUser",
            "email": "admin@test.com",
            "mobile": "+8613800138000",
            "region": "北京"
        }
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    return None

def test_contract_detail_with_creator():
    print("=" * 60)
    print("合同详情接口 - 创建人信息测试")
    print("=" * 60)
    
    token = get_auth_token()
    if not token:
        print("❌ 登录失败，无法获取认证令牌")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    contracts = []
    
    print("\n1. 测试合同列表（验证创建人信息）...")
    response = requests.get(
        f"{BASE_URL}/contracts",
        headers=headers
    )
    
    if response.status_code == 200:
        contracts = response.json()
        print(f"✅ 查询成功，返回 {len(contracts)} 条数据")
        
        if contracts:
            first_contract = contracts[0]
            print(f"\n   示例合同列表数据:")
            print(f"   - 合同ID: {first_contract.get('id')}")
            print(f"   - 合同名称: {first_contract.get('contract_name')}")
            print(f"   - 创建人ID: {first_contract.get('creator_id')}")
            
            creator_info = first_contract.get('creator_info')
            if creator_info:
                print(f"   ✅ 包含创建人信息:")
                print(f"      - 创建人ID: {creator_info.get('id')}")
                print(f"      - 创建人姓名: {creator_info.get('name')}")
                print(f"      - 创建人邮箱: {creator_info.get('email')}")
                print(f"      - 创建人手机: {creator_info.get('mobile')}")
                print(f"      - 创建人头像: {creator_info.get('avatar_url')}")
            else:
                print(f"   ⚠️  未包含创建人信息")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    print("\n2. 测试合同详情（验证创建人信息）...")
    if contracts and contracts[0].get('id'):
        contract_id = contracts[0]['id']
        response = requests.get(
            f"{BASE_URL}/contracts/{contract_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            contract = response.json()
            print(f"✅ 查询成功")
            
            print(f"\n   合同详情数据:")
            print(f"   - 合同ID: {contract.get('id')}")
            print(f"   - 合同名称: {contract.get('contract_name')}")
            print(f"   - 合同编号: {contract.get('contract_number')}")
            print(f"   - 创建人ID: {contract.get('creator_id')}")
            print(f"   - 客户信息: {contract.get('customer_info')}")
            print(f"   - 商机信息: {contract.get('opportunity_info')}")
            print(f"   - 联系人信息: {contract.get('contact_info')}")
            
            creator_info = contract.get('creator_info')
            if creator_info:
                print(f"   ✅ 包含完整创建人信息:")
                print(f"      - 创建人ID: {creator_info.get('id')}")
                print(f"      - 创建人姓名: {creator_info.get('name')}")
                print(f"      - 创建人邮箱: {creator_info.get('email')}")
                print(f"      - 创建人手机: {creator_info.get('mobile')}")
                print(f"      - 创建人头像: {creator_info.get('avatar_url')}")
            else:
                print(f"   ⚠️  未包含创建人信息")
            
            print(f"\n   完整响应数据:")
            print(json.dumps(contract, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"❌ 查询失败: {response.text}")
    else:
        print("⚠️  没有可用的合同数据进行详情测试")
    
    print("\n" + "=" * 60)
    print("✅ 合同详情接口测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    test_contract_detail_with_creator()
