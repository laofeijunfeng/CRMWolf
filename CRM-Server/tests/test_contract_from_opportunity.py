import requests

BASE_URL = "http://localhost:8000"

def test_create_contract_from_won_opportunity():
    print("=" * 60)
    print("测试从赢单商机创建合同")
    print("=" * 60)
    
    print("\n1. 获取认证token...")
    login_response = requests.post(f"{BASE_URL}/dev/mock-login", json={
        "name": "Eddie",
        "email": "eddie@test.com",
        "mobile": "+8613800138001",
        "region": "北京"
    })
    
    if login_response.status_code != 200:
        print(f"❌ 登录失败: {login_response.status_code}")
        print(login_response.text)
        return
    
    token = login_response.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ 登录成功")
    
    print("\n2. 检查赢单商机（ID=6）状态...")
    opp_response = requests.get(
        f"{BASE_URL}/api/v1/opportunities/6",
        headers=headers
    )
    
    if opp_response.status_code == 200:
        opportunity = opp_response.json()
        print(f"✅ 获取商机信息成功")
        print(f"   商机名称: {opportunity['opportunity_name']}")
        print(f"   商机状态: {opportunity['status']} (1=赢单)")
        print(f"   商机阶段: {opportunity['stage']['stage_name']}")
        print(f"   实际成交金额: {opportunity['actual_amount']}")
    else:
        print(f"❌ 获取商机失败: {opp_response.status_code}")
        print(opp_response.text)
        return
    
    print("\n3. 测试从赢单商机创建合同...")
    
    contract_response = requests.post(
        f"{BASE_URL}/api/v1/contracts/from-opportunity/6",
        params={
            "contract_name": "测试标记赢单-阶段更新-合同",
            "signing_contact_id": 12
        },
        headers=headers
    )
    
    if contract_response.status_code == 201:
        contract = contract_response.json()
        print(f"✅ 合同创建成功")
        print(f"   合同ID: {contract['id']}")
        print(f"   合同名称: {contract['contract_name']}")
        print(f"   合同编号: {contract['contract_number']}")
        print(f"   合同金额: {contract['total_amount']}")
        print(f"   商机ID: {contract['opportunity_id']}")
        print(f"   客户ID: {contract['customer_id']}")
    else:
        print(f"❌ 创建合同失败: {contract_response.status_code}")
        print(contract_response.text)
        return
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    test_create_contract_from_won_opportunity()
