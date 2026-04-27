import requests

BASE_URL = "http://localhost:8000"

def create_sales_director():
    """创建销售总监用户"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "测试用户",
            "email": "test_contract@example.com",
            "region": "北京"
        }
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    return None

def get_all_contracts(token):
    """获取所有合同"""
    response = requests.get(
        f"{BASE_URL}/api/v1/contracts/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def get_all_opportunities(token):
    """获取所有商机"""
    response = requests.get(
        f"{BASE_URL}/api/v1/opportunities/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def test_get_contract_by_opportunity(token, opportunity_id):
    """测试根据商机获取合同"""
    print(f"\n=== 测试：根据商机 {opportunity_id} 获取合同 ===")
    
    response = requests.get(
        f"{BASE_URL}/api/v1/contracts/opportunity/{opportunity_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        contract = response.json()
        print("✅ 成功获取合同")
        print(f"   合同ID: {contract['id']}")
        print(f"   合同编号: {contract['contract_number']}")
        print(f"   合同名称: {contract['contract_name']}")
        print(f"   商机ID: {contract['opportunity_id']}")
        if contract.get('customer_info'):
            print(f"   客户名称: {contract['customer_info']['account_name']}")
        if contract.get('opportunity_info'):
            print(f"   商机名称: {contract['opportunity_info']['opportunity_name']}")
        return contract
    elif response.status_code == 404:
        print("✅ 正确返回404：该商机暂无合同")
        return None
    else:
        print(f"❌ 请求失败")
        print(f"   响应: {response.text}")
        return None

def main():
    print("=" * 60)
    print("根据商机获取合同接口测试")
    print("=" * 60)
    
    print("\n1. 创建销售总监用户...")
    token = create_sales_director()
    if not token:
        print("❌ 创建用户失败")
        return
    print("✅ 用户创建成功")
    
    print("\n2. 获取所有商机...")
    opportunities = get_all_opportunities(token)
    if not opportunities or len(opportunities) == 0:
        print("❌ 没有找到商机，请先创建商机")
        return
    
    print(f"✅ 找到 {len(opportunities)} 个商机")
    test_opportunity = opportunities[0]
    opportunity_id = test_opportunity['id']
    print(f"   选择商机: {test_opportunity['opportunity_name']} (ID: {opportunity_id})")
    
    print("\n3. 测试：获取商机关联的合同（第一次）...")
    test_get_contract_by_opportunity(token, opportunity_id)
    
    print("\n4. 获取所有合同...")
    contracts = get_all_contracts(token)
    if contracts and len(contracts) > 0:
        print(f"✅ 找到 {len(contracts)} 个合同")
        test_contract = contracts[0]
        print(f"   选择合同: {test_contract['contract_name']} (ID: {test_contract['id']})")
        print(f"   关联商机ID: {test_contract['opportunity_id']}")
        
        print("\n5. 测试：获取该商机关联的合同（第二次）...")
        test_get_contract_by_opportunity(token, test_contract['opportunity_id'])
    else:
        print("⚠️  没有找到合同，无法测试完整流程")
    
    print("\n6. 测试：使用不存在的商机ID...")
    test_get_contract_by_opportunity(token, 99999)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n新接口说明：")
    print("- 路径: GET /api/v1/contracts/opportunity/{opportunity_id}")
    print("- 功能: 根据商机ID获取关联的合同")
    print("- 返回: 200 - 找到合同，404 - 该商机暂无合同")
    print("- 特点: 返回客户和商机的基本信息")

if __name__ == "__main__":
    main()
