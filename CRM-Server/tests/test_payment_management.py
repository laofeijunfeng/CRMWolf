#!/usr/bin/env python3
"""回款管理功能测试脚本"""

import requests
from datetime import date, timedelta
from typing import Dict, Any

BASE_URL = "http://localhost:8000"


def get_auth_token() -> str:
    """获取认证token"""
    response = requests.post(f"{BASE_URL}/dev/mock-login", json={
        "name": "AdminUser",
        "email": "admin@test.com",
        "mobile": "+8613800138000",
        "region": "北京"
    })
    return response.json()["access_token"]


def test_payment_management():
    print("=" * 60)
    print("回款管理功能测试")
    print("=" * 60)
    
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 查询合同
    print("\n1. 查询合同列表...")
    response = requests.get(f"{BASE_URL}/api/v1/contracts", headers=headers)
    contracts = response.json()
    
    if not contracts:
        print("❌ 未找到合同，请先创建合同")
        return
    
    # 找到已签署或已生效的合同
    contract = None
    for c in contracts:
        if c["status"] in ["SIGNED", "EFFECTIVE"]:
            contract = c
            break
    
    if not contract:
        print("ℹ️  未找到已签署或已生效的合同，使用第一个合同")
        contract = contracts[0]
    
    contract_id = contract["id"]
    print(f"✅ 使用合同: {contract['contract_name']} (ID: {contract_id})")
    print(f"   合同状态: {contract['status']}")
    print(f"   合同金额: {contract['total_amount']}")
    
    # 2. 创建回款计划
    print("\n2. 创建回款计划...")
    payment_plans_data = {
        "plans": [
            {
                "stage_name": "首付款",
                "planned_amount": float(contract['total_amount']) * 0.3,
                "due_date": (date.today() + timedelta(days=7)).isoformat(),
                "notes": "合同签署后支付"
            },
            {
                "stage_name": "中期款",
                "planned_amount": float(contract['total_amount']) * 0.4,
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "notes": "项目交付后支付"
            },
            {
                "stage_name": "尾款",
                "planned_amount": float(contract['total_amount']) * 0.3,
                "due_date": (date.today() + timedelta(days=60)).isoformat(),
                "notes": "验收合格后支付"
            }
        ]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/payments/contracts/{contract_id}/payment-plans",
        json=payment_plans_data,
        headers=headers
    )
    
    if response.status_code != 201:
        print(f"❌ 创建回款计划失败: {response.text}")
        return
    
    plans = response.json()
    print(f"✅ 成功创建 {len(plans)} 条回款计划:")
    for plan in plans:
        print(f"   - {plan['stage_name']}: {plan['planned_amount']} 元，到期日: {plan['due_date']}")
    
    # 3. 查询回款计划列表
    print("\n3. 查询回款计划列表...")
    response = requests.get(
        f"{BASE_URL}/api/v1/payments/contracts/{contract_id}/payment-plans",
        headers=headers
    )
    plans = response.json()
    print(f"✅ 查询到 {len(plans)} 条回款计划")
    
    # 4. 查询回款汇总
    print("\n4. 查询回款汇总...")
    response = requests.get(
        f"{BASE_URL}/api/v1/payments/contracts/{contract_id}/payment-summary",
        headers=headers
    )
    summary = response.json()
    print(f"✅ 回款汇总:")
    print(f"   合同总额: {summary['total_amount']} 元")
    print(f"   已回款: {summary['total_paid_amount']} 元")
    print(f"   回款状态: {summary['payment_status']}")
    print(f"   计划数量: {summary['payment_plans_count']}")
    print(f"   已完成: {summary['completed_plans_count']}")
    print(f"   已逾期: {summary['overdue_plans_count']}")
    print(f"   待回款: {summary['remaining_amount']} 元")
    
    # 5. 登记回款
    print("\n5. 登记回款...")
    first_plan = plans[0]
    payment_data = {
        "actual_amount": float(first_plan['planned_amount']),
        "payment_date": date.today().isoformat(),
        "notes": "首付款已到账"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v1/payments/payment-plans/{first_plan['id']}/records",
        json=payment_data,
        headers=headers
    )
    
    if response.status_code == 201:
        record = response.json()
        print(f"✅ 成功登记回款:")
        print(f"   回款金额: {record['actual_amount']} 元")
        print(f"   回款日期: {record['payment_date']}")
    else:
        print(f"❌ 登记回款失败: {response.text}")
        return
    
    # 6. 再次查询回款汇总
    print("\n6. 再次查询回款汇总...")
    response = requests.get(
        f"{BASE_URL}/api/v1/payments/contracts/{contract_id}/payment-summary",
        headers=headers
    )
    summary = response.json()
    print(f"✅ 更新后的回款汇总:")
    print(f"   已回款: {summary['total_paid_amount']} 元")
    print(f"   回款状态: {summary['payment_status']}")
    print(f"   已完成: {summary['completed_plans_count']}")
    
    # 7. 查询回款记录
    print("\n7. 查询回款记录...")
    response = requests.get(
        f"{BASE_URL}/api/v1/payments/payment-plans/{first_plan['id']}/records",
        headers=headers
    )
    records = response.json()
    print(f"✅ 查询到 {len(records)} 条回款记录")
    for record in records:
        print(f"   - {record['actual_amount']} 元，日期: {record['payment_date']}，登记人: {record.get('creator_name', 'N/A')}")
    
    # 8. 测试即将到期提醒
    print("\n8. 查询即将到期的回款...")
    response = requests.get(
        f"{BASE_URL}/api/v1/payments/reminders/upcoming?days=7",
        headers=headers
    )
    
    if response.status_code == 200:
        upcoming = response.json()
        if isinstance(upcoming, list):
            print(f"✅ 未来7天内即将到期的回款: {len(upcoming)} 条")
            for reminder in upcoming[:3]:
                if isinstance(reminder, dict):
                    print(f"   - {reminder.get('contract_name', 'N/A')} - {reminder.get('stage_name', 'N/A')}: {reminder.get('planned_amount', 0)} 元，还有 {reminder.get('days_until_due', 0)} 天")
        else:
            print(f"ℹ️  提醒功能返回: {upcoming}")
    else:
        print(f"ℹ️  提醒功能状态码: {response.status_code}")
    
    print("\n" + "=" * 60)
    print("✅ 回款管理功能测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_payment_management()
