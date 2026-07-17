import requests
from datetime import date, datetime, timedelta

BASE_URL = "http://localhost:8000"

def create_sales_director():
    """创建销售总监用户"""
    response = requests.post(
        f"{BASE_URL}/dev/create-sales-director",
        json={
            "name": "销售总监",
            "email": "director_contract@example.com",
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

def get_all_opportunities(token):
    """获取所有商机"""
    response = requests.get(
        f"{BASE_URL}/api/v1/opportunities/",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def get_customer_contacts(token, customer_id):
    """获取客户联系人"""
    response = requests.get(
        f"{BASE_URL}/api/v1/customers/{customer_id}/contacts",
        headers={"Authorization": f"Bearer {token}"}
    )
    if response.status_code == 200:
        return response.json()
    return None

def test_create_contract(token, customer_id, opportunity_id, signing_contact_id):
    """测试创建合同"""
    print("\n=== 测试创建合同 ===")
    
    contract_data = {
        "contract_name": "星辰科技-飞书CRM私有化部署合同",
        "customer_id": customer_id,
        "opportunity_id": opportunity_id,
        "signing_contact_id": signing_contact_id,
        "user_count": 50,
        "total_amount": "250000.00",
        "license_type": "PERPETUAL",
        "signing_date": str(date.today()),
        "effective_date": str(date.today() + timedelta(days=7))
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/contracts/",
        json=contract_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 201:
        data = response.json()
        print("✅ 合同创建成功！")
        print(f"   合同ID: {data['id']}")
        print(f"   合同编号: {data['contract_number']}")
        print(f"   合同名称: {data['contract_name']}")
        print(f"   合同总金额: ¥{data['total_amount']}")
        print(f"   标准单价: ¥{data['standard_unit_price']}")
        print(f"   授权模式: {data['license_type']}")
        print(f"   合同状态: {data['status']}")
        return data
    else:
        print(f"❌ 创建合同失败: {response.status_code}")
        print(response.text)
        return None

def test_get_contracts(token):
    """测试获取合同列表"""
    print("\n=== 测试获取合同列表 ===")
    
    response = requests.get(
        f"{BASE_URL}/api/v1/contracts/",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        contracts = response.json()
        print(f"✅ 获取到 {len(contracts)} 个合同")
        for contract in contracts:
            print(f"   - {contract['contract_number']}: {contract['contract_name']}")
        return contracts
    else:
        print(f"❌ 获取合同列表失败: {response.status_code}")
        return None

def test_get_contract_detail(token, contract_id):
    """测试获取合同详情"""
    print("\n=== 测试获取合同详情 ===")
    
    response = requests.get(
        f"{BASE_URL}/api/v1/contracts/{contract_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        contract = response.json()
        print("✅ 获取合同详情成功！")
        print(f"   合同编号: {contract['contract_number']}")
        print(f"   合同名称: {contract['contract_name']}")
        if contract.get('customer_info'):
            print(f"   客户名称: {contract['customer_info']['account_name']}")
        if contract.get('opportunity_info'):
            print(f"   商机名称: {contract['opportunity_info']['opportunity_name']}")
        if contract.get('contact_info'):
            print(f"   签约人: {contract['contact_info']['name']} ({contract['contact_info']['mobile']})")
        return contract
    else:
        print(f"❌ 获取合同详情失败: {response.status_code}")
        return None

def test_customer_contracts(token, customer_id):
    """测试获取客户合同列表"""
    print("\n=== 测试获取客户合同列表 ===")
    
    response = requests.get(
        f"{BASE_URL}/api/v1/contracts/customer/{customer_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        contracts = response.json()
        print(f"✅ 客户有 {len(contracts)} 个合同")
        return contracts
    else:
        print(f"❌ 获取客户合同列表失败: {response.status_code}")
        return None

def test_subscription_contract(token, customer_id, opportunity_id, signing_contact_id):
    """测试创建订阅制合同"""
    print("\n=== 测试创建订阅制合同 ===")
    
    contract_data = {
        "contract_name": "星辰科技-飞书CRM年度订阅合同",
        "customer_id": customer_id,
        "opportunity_id": opportunity_id,
        "signing_contact_id": signing_contact_id,
        "user_count": 100,
        "total_amount": "120000.00",
        "license_type": "SUBSCRIPTION",
        "subscription_years": 2,
        "effective_date": str(date.today() + timedelta(days=7))
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/contracts/",
        json=contract_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 201:
        data = response.json()
        print("✅ 订阅制合同创建成功！")
        print(f"   合同编号: {data['contract_number']}")
        print(f"   订阅年限: {data['subscription_years']} 年")
        print(f"   标准单价: ¥{data['standard_unit_price']} (年/用户)")
        print(f"   到期日期: {data.get('expiry_date', '未计算')}")
        return data
    else:
        print(f"❌ 创建订阅制合同失败: {response.status_code}")
        return None

def main():
    print("=" * 50)
    print("合同管理模块测试")
    print("=" * 50)
    
    print("\n1. 创建销售总监用户...")
    token = create_sales_director()
    if not token:
        print("❌ 创建用户失败")
        return
    print("✅ 用户创建成功")
    
    print("\n2. 获取测试数据（客户、商机、联系人）...")
    customers = get_all_customers(token)
    if not customers or len(customers) == 0:
        print("❌ 没有找到客户，请先创建客户")
        return
    
    opportunities = get_all_opportunities(token)
    if not opportunities or len(opportunities) == 0:
        print("❌ 没有找到商机，请先创建商机")
        return
    
    customer_id = customers[0]['id']
    print(f"   使用客户ID: {customer_id}")
    
    opportunity_id = opportunities[0]['id']
    print(f"   使用商机ID: {opportunity_id}")
    
    contacts = get_customer_contacts(token, customer_id)
    if not contacts or len(contacts) == 0:
        print("❌ 没有找到联系人，请先创建联系人")
        return
    
    signing_contact_id = contacts[0]['id']
    print(f"   使用联系人ID: {signing_contact_id}")
    
    contract = test_create_contract(token, customer_id, opportunity_id, signing_contact_id)
    if not contract:
        return
    
    test_get_contracts(token)
    
    test_get_contract_detail(token, contract['id'])
    
    test_customer_contracts(token, customer_id)
    
    test_subscription_contract(token, customer_id, opportunity_id, signing_contact_id)
    
    print("\n" + "=" * 50)
    print("✅ 所有测试完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()
