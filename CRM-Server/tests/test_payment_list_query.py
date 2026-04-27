#!/usr/bin/env python3
"""
测试回款计划列表查询API
"""
import requests
from datetime import date, timedelta
import json

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


def test_list_payment_plans():
    print("=" * 60)
    print("回款计划列表查询API测试")
    print("=" * 60)
    
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 基础查询（无筛选条件）
    print("\n1. 基础查询（无筛选条件）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans",
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
    
    # 2. 按状态筛选
    print("\n2. 按状态筛选（PENDING）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans?status=PENDING",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   待回款计划数: {data['total']}")
        if data['items']:
            print(f"   示例: {data['items'][0]['contract_name']} - {data['items'][0]['stage_name']}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 3. 查询自己的计划
    print("\n3. 查询当前用户的计划...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans?me=true",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   我的计划数: {data['total']}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 4. 按日期范围筛选
    print("\n4. 按日期范围筛选（未来30天）...")
    start_date = date.today()
    end_date = date.today() + timedelta(days=30)
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans",
        params={
            "due_date_start": start_date.isoformat(),
            "due_date_end": end_date.isoformat()
        },
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   未来30天到期计划数: {data['total']}")
        if data['items']:
            for item in data['items'][:3]:
                print(f"   - {item['stage_name']}: {item['planned_amount']} 元，到期日: {item['due_date']}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 5. 组合筛选
    print("\n5. 组合筛选（状态 + 日期范围 + 分页）...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans",
        params={
            "status": "PENDING",
            "due_date_start": start_date.isoformat(),
            "due_date_end": end_date.isoformat(),
            "page": 1,
            "page_size": 5
        },
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 查询成功")
        print(f"   待回款且在未来30天到期的计划数: {data['total']}")
        print(f"   当前页返回: {len(data['items'])} 条")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 6. 测试分页
    print("\n6. 测试分页...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans?page=1&page_size=3",
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
                f"{BASE_URL}/payments/payment-plans?page=2&page_size=3",
                headers=headers
            )
            if response.status_code == 200:
                data2 = response.json()
                print(f"✅ 第2页查询成功")
                print(f"   第2页返回: {len(data2['items'])} 条")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    # 7. 验证返回字段
    print("\n7. 验证返回字段...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans?page=1&page_size=1",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if data['items']:
            item = data['items'][0]
            print(f"✅ 字段验证:")
            print(f"   - id: {item.get('id')}")
            print(f"   - contract_id: {item.get('contract_id')}")
            print(f"   - stage_name: {item.get('stage_name')}")
            print(f"   - planned_amount: {item.get('planned_amount')}")
            print(f"   - paid_amount: {item.get('paid_amount')}")
            print(f"   - remaining_amount: {item.get('remaining_amount')}")
            print(f"   - status: {item.get('status')}")
            print(f"   - due_date: {item.get('due_date')}")
    else:
        print(f"❌ 查询失败: {response.text}")
    
    print("\n" + "=" * 60)
    print("✅ 回款计划列表查询API测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_list_payment_plans()
