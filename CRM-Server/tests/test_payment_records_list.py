#!/usr/bin/env python3
"""
测试回款记录列表查询API
"""
import requests
from datetime import date, timedelta

BASE_URL = "http://localhost:8000/api/v1"


def get_auth_token():
    print("正在登录...")
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
        token = response.json()["access_token"]
        print("✅ 登录成功")
        return token
    else:
        print(f"❌ 登录失败: {response.text}")
        exit(1)


def test_payment_records_list():
    print("=" * 60)
    print("回款记录列表查询API测试")
    print("=" * 60)
    
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 基础查询（无筛选条件）
    print("\n1. 基础查询（无筛选条件）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   总数: {data['total']}")
        print(f"   当前页: {data['page']}")
        print(f"   每页大小: {data['page_size']}")
        print(f"   总页数: {data['total_pages']}")
        print(f"   返回数据: {len(data['items'])} 条")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 2. 按合同筛选
    print("\n2. 按合同筛选（contract_id=1）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records?contract_id=1",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   合同1的回款记录数: {data['total']}")
        if data['items']:
            item = data['items'][0]
            print(f"   示例: {item['contract_name']} - {item['stage_name']}: {item['actual_amount']} 元")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 3. 按回款计划筛选
    print("\n3. 按回款计划筛选（payment_plan_id=1）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records?payment_plan_id=1",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   回款计划1的记录数: {data['total']}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 4. 按日期范围筛选
    print("\n4. 按日期范围筛选（最近30天）...")
    start_date = date.today() - timedelta(days=30)
    end_date = date.today()
    response = requests.get(
        f"{BASE_URL}/payments/payment-records",
        params={
            "payment_date_start": start_date.isoformat(),
            "payment_date_end": end_date.isoformat()
        },
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   最近30天的回款记录数: {data['total']}")
        if data['items']:
            for item in data['items'][:3]:
                print(f"   - {item['payment_date']}: {item['actual_amount']} 元")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 5. 按金额筛选
    print("\n5. 按金额筛选（min_amount=50000）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records?min_amount=50000",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   金额≥50000的记录数: {data['total']}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 6. 查询自己的记录
    print("\n6. 查询当前用户的记录...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records?me=true",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   我登记的记录数: {data['total']}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 7. 组合筛选
    print("\n7. 组合筛选（合同 + 日期 + 分页）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records",
        params={
            "contract_id": 1,
            "payment_date_start": start_date.isoformat(),
            "payment_date_end": end_date.isoformat(),
            "page": 1,
            "page_size": 5
        },
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   合同1在最近30天的回款记录数: {data['total']}")
        print(f"   当前页返回: {len(data['items'])} 条")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 8. 测试分页
    print("\n8. 测试分页...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records?page=1&page_size=3",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 第1页查询成功")
        print(f"   总数: {data['total']}")
        print(f"   每页3条，共 {data['total_pages']} 页")
        print(f"   第1页返回: {len(data['items'])} 条")
        
        # 如果有第2页，查询第2页
        if data['total_pages'] >= 2:
            response = requests.get(
                f"{BASE_URL}/payments/payment-records?page=2&page_size=3",
                headers=headers
            )
            if response.status_code == 200:
                data2 = response.json()
                print(f"✅ 第2页查询成功")
                print(f"   第2页返回: {len(data2['items'])} 条")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 9. 验证返回字段
    print("\n9. 验证返回字段...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-records?page=1&page_size=1",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if data['items']:
            item = data['items'][0]
            print(f"✅ 字段验证:")
            print(f"   - id: {item.get('id')}")
            print(f"   - payment_plan_id: {item.get('payment_plan_id')}")
            print(f"   - actual_amount: {item.get('actual_amount')}")
            print(f"   - payment_date: {item.get('payment_date')}")
            print(f"   - contract_id: {item.get('contract_id')}")
            print(f"   - contract_name: {item.get('contract_name')}")
            print(f"   - stage_name: {item.get('stage_name')}")
            print(f"   - creator_name: {item.get('creator_name')}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    print("\n" + "=" * 60)
    print("✅ 回款记录列表查询API测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_payment_records_list()
