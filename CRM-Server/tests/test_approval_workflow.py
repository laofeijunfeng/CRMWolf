import requests
import time

BASE_URL = "http://localhost:8000"

def test_approval_workflow():
    print("=" * 60)
    print("合同审批流程测试")
    print("=" * 60)
    
    print("\n1. 创建用户并获取token...")
    login_response = requests.post(f"{BASE_URL}/dev/mock-login", json={
        "name": "SalesUser",
        "email": "sales@test.com",
        "mobile": "+8613800138003",
        "region": "北京"
    })
    
    if login_response.status_code != 200:
        print(f"❌ 创建销售用户失败: {login_response.status_code}")
        return
    
    token = login_response.json().get("access_token")
    user_info = login_response.json().get("user")
    sales_user_id = user_info.get("id")
    sales_feishu_id = user_info.get("feishu_open_id")
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ 销售用户创建成功")
    
    print("\n2. 创建销售总监用户用于审批...")
    director_response = requests.post(f"{BASE_URL}/dev/create-sales-director", json={
        "name": "Director",
        "email": "director@test.com",
        "region": "北京"
    })
    
    if director_response.status_code == 200:
        director_token = director_response.json().get("access_token")
        director_headers = {"Authorization": f"Bearer {director_token}"}
        print("✅ 销售总监创建成功")
    else:
        print(f"⚠️  销售总监已存在")
        director_response = requests.post(f"{BASE_URL}/dev/mock-login", json={
            "name": "Director",
            "email": "director@test.com",
            "mobile": "+8613800138001",
            "region": "北京"
        })
        if director_response.status_code == 200:
            director_token = director_response.json().get("access_token")
            director_headers = {"Authorization": f"Bearer {director_token}"}
            print("✅ 使用已有销售总监")
        else:
            print("❌ 获取销售总监token失败")
            return
    
    print("\n3. 获取或创建测试数据...")
    customers_response = requests.get(f"{BASE_URL}/api/v1/customers/", headers=headers)
    if customers_response.status_code != 200 or len(customers_response.json()) == 0:
        print("❌ 没有找到客户，请先创建客户")
        return
    
    customer_id = customers_response.json()[0]['id']
    print(f"   使用客户ID: {customer_id}")
    
    opportunities_response = requests.get(f"{BASE_URL}/api/v1/opportunities/", headers=headers)
    if opportunities_response.status_code != 200 or len(opportunities_response.json()) == 0:
        print("❌ 没有找到商机，请先创建商机")
        return
    
    opportunity_id = opportunities_response.json()[0]['id']
    print(f"   使用商机ID: {opportunity_id}")
    
    contacts_response = requests.get(f"{BASE_URL}/api/v1/customers/{customer_id}/contacts", headers=headers)
    if contacts_response.status_code != 200 or len(contacts_response.json()) == 0:
        print("❌ 没有找到联系人，请先创建联系人")
        return
    
    contact_id = contacts_response.json()[0]['id']
    print(f"   使用联系人ID: {contact_id}")
    
    print("\n4. 创建测试合同...")
    contract_data = {
        "contract_name": "测试审批流程-小额合同",
        "customer_id": customer_id,
        "opportunity_id": opportunity_id,
        "signing_contact_id": contact_id,
        "user_count": 10,
        "total_amount": "50000.00",
        "license_type": "PERPETUAL"
    }
    
    contract_response = requests.post(
        f"{BASE_URL}/api/v1/contracts/",
        json=contract_data,
        headers=headers
    )
    
    if contract_response.status_code != 201:
        print(f"❌ 创建合同失败: {contract_response.status_code}")
        print(contract_response.text)
        return
    
    contract = contract_response.json()
    contract_id = contract['id']
    print(f"✅ 合同创建成功，ID: {contract_id}")
    print(f"   合同状态: {contract['status']}")
    
    print("\n5. 提交审批...")
    submit_response = requests.post(
        f"{BASE_URL}/api/v1/approvals/contracts/{contract_id}/submit",
        json={"comment": "请审批"},
        headers=headers
    )
    
    if submit_response.status_code != 201:
        print(f"❌ 提交审批失败: {submit_response.status_code}")
        print(submit_response.text)
        return
    
    approval = submit_response.json()
    print(f"✅ 审批提交成功")
    print(f"   审批ID: {approval['id']}")
    print(f"   审批状态: {approval['status']}")
    print(f"   当前节点: {approval.get('current_node_name', 'N/A')}")
    
    print("\n6. 查询审批详情...")
    detail_response = requests.get(
        f"{BASE_URL}/api/v1/approvals/contracts/{contract_id}/detail",
        headers=headers
    )
    
    if detail_response.status_code == 200:
        detail = detail_response.json()
        print("✅ 获取审批详情成功")
        print(f"   审批流程: {detail.get('flow', {}).get('flow_name', 'N/A')}")
        print(f"   审批记录数: {len(detail.get('records', []))}")
    
    print("\n7. 销售总监审批通过...")
    approve_response = requests.post(
        f"{BASE_URL}/api/v1/approvals/contracts/{contract_id}/approve",
        json={"action": "APPROVE", "comment": "同意"},
        headers=director_headers
    )
    
    if approve_response.status_code == 200:
        approval = approve_response.json()
        print(f"✅ 审批操作成功")
        print(f"   审批状态: {approval['status']}")
        if approval['status'] == 'APPROVED':
            print(f"   当前节点: {approval.get('current_node_name', 'N/A')}")
        else:
            print(f"   当前节点: {approval.get('current_node_name', 'N/A')}")
    else:
        print(f"❌ 审批操作失败: {approve_response.status_code}")
        print(approve_response.text)
    
    print("\n8. 验证合同状态...")
    contract_check = requests.get(
        f"{BASE_URL}/api/v1/contracts/{contract_id}",
        headers=headers
    )
    
    if contract_check.status_code == 200:
        contract_updated = contract_check.json()
        print(f"✅ 合同状态已更新: {contract_updated['status']}")
    
    print("\n" + "=" * 60)
    print("✅ 审批流程测试完成！")
    print("=" * 60)


def test_multi_level_approval():
    print("\n\n" + "=" * 60)
    print("多级审批流程测试（大额合同）")
    print("=" * 60)
    
    print("\n1. 创建销售用户...")
    login_response = requests.post(f"{BASE_URL}/dev/mock-login", json={
        "name": "BigSales",
        "email": "bigsales@test.com",
        "mobile": "+8613800138004",
        "region": "上海"
    })
    
    if login_response.status_code != 200:
        print(f"❌ 创建用户失败")
        return
    
    token = login_response.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    user_info = login_response.json().get("user")
    print("✅ 销售用户创建成功")
    
    print("\n2. 获取测试数据...")
    customers_response = requests.get(f"{BASE_URL}/api/v1/customers/", headers=headers)
    if customers_response.status_code != 200:
        print("❌ 获取客户失败")
        return
    
    customer_id = customers_response.json()[0]['id']
    
    opportunities_response = requests.get(f"{BASE_URL}/api/v1/opportunities/", headers=headers)
    opportunity_id = opportunities_response.json()[0]['id']
    
    contacts_response = requests.get(f"{BASE_URL}/api/v1/customers/{customer_id}/contacts", headers=headers)
    contact_id = contacts_response.json()[0]['id']
    
    print(f"   客户ID: {customer_id}, 商机ID: {opportunity_id}, 联系人ID: {contact_id}")
    
    print("\n3. 创建大额合同（60万，需要三级审批）...")
    contract_data = {
        "contract_name": "测试多级审批-大额合同",
        "customer_id": customer_id,
        "opportunity_id": opportunity_id,
        "signing_contact_id": contact_id,
        "user_count": 50,
        "total_amount": "600000.00",
        "license_type": "SUBSCRIPTION",
        "subscription_years": 2
    }
    
    contract_response = requests.post(
        f"{BASE_URL}/api/v1/contracts/",
        json=contract_data,
        headers=headers
    )
    
    if contract_response.status_code != 201:
        print(f"❌ 创建合同失败")
        return
    
    contract = contract_response.json()
    contract_id = contract['id']
    print(f"✅ 合同创建成功，ID: {contract_id}")
    
    print("\n4. 提交审批...")
    submit_response = requests.post(
        f"{BASE_URL}/api/v1/approvals/contracts/{contract_id}/submit",
        json={"comment": "请审批大额合同"},
        headers=headers
    )
    
    if submit_response.status_code != 201:
        print(f"❌ 提交审批失败")
        print(submit_response.text)
        return
    
    approval = submit_response.json()
    print(f"✅ 审批提交成功")
    print(f"   当前节点: {approval.get('current_node_name', 'N/A')}")
    print(f"   审批流程: {approval.get('flow_name', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("✅ 多级审批测试准备完成！")
    print("   请手动进行后续审批操作测试")
    print("=" * 60)


if __name__ == "__main__":
    test_approval_workflow()
    test_multi_level_approval()
