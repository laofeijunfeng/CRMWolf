"""
测试客户退回公海功能
"""
import requests
import json


BASE_URL = "http://localhost:8000"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1IiwiZXhwIjoxNzcwMTI2ODI0fQ.riWBVItiYnn5-jzZNxES8g5iMU5Tlqf8aTWwXigcD8I"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}


def test_get_customers():
    print("\n1. 查询当前客户列表")
    response = requests.get(f"{BASE_URL}/api/v1/customers/", headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        customers = response.json()
        print(f"客户数量: {len(customers)}")
        for customer in customers[:3]:
            print(f"  - ID: {customer['id']}, 名称: {customer['account_name']}, 负责人: {customer['owner_id']}")
        return customers
    else:
        print(f"错误: {response.text}")
        return []


def test_get_public_customers():
    print("\n2. 查询公海客户列表")
    response = requests.get(f"{BASE_URL}/api/v1/customers/public/list", headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        customers = response.json()
        print(f"公海客户数量: {len(customers)}")
        for customer in customers[:3]:
            print(f"  - ID: {customer['id']}, 名称: {customer['account_name']}, 退回原因: {customer.get('return_reason', 'N/A')}")
        return customers
    else:
        print(f"错误: {response.text}")
        return []


def test_return_customer(customer_id, return_reason, detailed_reason=None):
    print(f"\n3. 退回客户到公海 (ID: {customer_id})")
    data = {
        "return_reason": return_reason
    }
    if detailed_reason:
        data["detailed_reason"] = detailed_reason
    
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/return-to-pool",
        headers=headers,
        json=data
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"成功: {result['message']}")
        print(f"  原负责人: {result['previous_owner']}")
        print(f"  退回时间: {result['returned_time']}")
        print(f"  退回原因: {result['return_reason']}")
        return True
    else:
        print(f"错误: {response.text}")
        return False


def test_claim_customer(customer_id, owner_id):
    print(f"\n4. 领取公海客户 (ID: {customer_id})")
    data = {
        "owner_id": owner_id
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/customers/{customer_id}/claim",
        headers=headers,
        json=data
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        customer = response.json()
        print(f"领取成功: {customer['account_name']}")
        print(f"  新负责人: {customer['owner_id']}")
        return True
    else:
        print(f"错误: {response.text}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("客户退回公海功能测试")
    print("=" * 60)
    
    customers = test_get_customers()
    
    if customers:
        print("\n" + "=" * 60)
        print("测试退回客户功能")
        print("=" * 60)
        
        first_customer = customers[0]
        customer_id = first_customer['id']
        
        success = test_return_customer(
            customer_id,
            return_reason="丢单",
            detailed_reason="客户最终选择了竞争对手的解决方案"
        )
        
        if success:
            print("\n" + "=" * 60)
            print("验证退回后的数据")
            print("=" * 60)
            
            test_get_customers()
            test_get_public_customers()
            
            print("\n" + "=" * 60)
            print("测试领取客户功能")
            print("=" * 60)
            
            test_claim_customer(customer_id, "mock_open_id_Harry")
            
            print("\n" + "=" * 60)
            print("测试完成")
            print("=" * 60)
    else:
        print("没有可用的客户进行测试")
