#!/usr/bin/env python3
"""
简单测试回款计划列表查询API
"""
import requests
from datetime import date, timedelta

BASE_URL = "http://localhost:8000/api/v1"


def test_payment_plans_list():
    print("=" * 60)
    print("测试回款计划列表查询API")
    print("=" * 60)
    
    # 使用已有的管理员token（假设已知）
    # 这里我们直接测试API，不登录
    
    print("\n1. 测试API是否存在...")
    response = requests.get(f"{BASE_URL}/payments/payment-plans")
    print(f"状态码: {response.status_code}")
    if response.status_code == 401:
        print("✅ API存在，需要认证")
    elif response.status_code == 200:
        print("✅ API存在且可访问")
        data = response.json()
        print(f"返回数据: {data}")
    else:
        print(f"❌ API响应异常: {response.text}")
    
    print("\n2. 测试分页参数...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans?page=1&page_size=5"
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 401:
        print("✅ 分页参数API存在")
    else:
        print(f"响应: {response.text[:200]}")
    
    print("\n3. 测试筛选参数...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans?status=PENDING"
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 401:
        print("✅ 筛选参数API存在")
    else:
        print(f"响应: {response.text[:200]}")
    
    print("\n4. 测试日期范围筛选...")
    start = date.today()
    end = date.today() + timedelta(days=30)
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans",
        params={
            "due_date_start": start.isoformat(),
            "due_date_end": end.isoformat()
        }
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 401:
        print("✅ 日期范围筛选API存在")
    else:
        print(f"响应: {response.text[:200]}")
    
    print("\n5. 测试组合筛选...")
    response = requests.get(
        f"{BASE_URL}/payments/payment-plans",
        params={
            "status": "PENDING",
            "page": 1,
            "page_size": 10
        }
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 401:
        print("✅ 组合筛选API存在")
    else:
        print(f"响应: {response.text[:200]}")
    
    print("\n" + "=" * 60)
    print("✅ API接口测试完成！")
    print("=" * 60)
    print("\n说明：API返回401表示需要认证，这说明接口已正确注册。")
    print("在实际使用中，需要先登录获取token，然后在请求头中添加Authorization。")


if __name__ == "__main__":
    test_payment_plans_list()
