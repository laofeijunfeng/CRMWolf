import requests
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_mark_win_updates_stage():
    print("=" * 60)
    print("测试标记赢单接口是否正确更新阶段")
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
    user_info = login_response.json().get("user")
    feishu_open_id = user_info.get("feishu_open_id")
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ 登录成功")
    print(f"   用户ID: {feishu_open_id}")
    
    print("\n2. 创建测试商机...")
    create_data = {
        "opportunity_name": "测试标记赢单-阶段更新",
        "customer_id": 11,
        "total_amount": 500000.00,
        "user_count": 100,
        "license_type": "SUBSCRIPTION",
        "subscription_years": 1,
        "purchase_type": "NEW",
        "expected_closing_date": "2025-12-31",
        "stage_id": 1,
        "owner_id": feishu_open_id
    }
    
    create_response = requests.post(
        f"{BASE_URL}/api/v1/opportunities/",
        json=create_data,
        headers=headers
    )
    
    if create_response.status_code != 201:
        print(f"❌ 创建商机失败: {create_response.status_code}")
        print(create_response.text)
        return
    
    opportunity = create_response.json()
    opportunity_id = opportunity['id']
    print(f"✅ 商机创建成功，ID: {opportunity_id}")
    print(f"   初始阶段ID: {opportunity['stage_id']}")
    print(f"   初始状态: {opportunity['status']}")
    print(f"   初始赢率: {opportunity['win_probability']}%")
    
    print("\n3. 标记赢单...")
    win_data = {
        "actual_amount": 480000.00,
        "actual_closing_date": "2025-12-20"
    }
    
    win_response = requests.patch(
        f"{BASE_URL}/api/v1/opportunities/{opportunity_id}/win",
        json=win_data,
        headers=headers
    )
    
    if win_response.status_code != 200:
        print(f"❌ 标记赢单失败: {win_response.status_code}")
        print(win_response.text)
        return
    
    updated_opportunity = win_response.json()
    print(f"✅ 标记赢单成功")
    print(f"   更新后阶段ID: {updated_opportunity['stage_id']}")
    print(f"   更新后状态: {updated_opportunity['status']}")
    print(f"   更新后赢率: {updated_opportunity['win_probability']}%")
    print(f"   实际成交金额: {updated_opportunity['actual_amount']}")
    print(f"   实际成交日期: {updated_opportunity['actual_closing_date']}")
    
    print("\n4. 验证阶段是否正确更新...")
    if updated_opportunity['stage_id'] == 5:
        print("✅ 阶段已正确更新为'赢单'阶段（ID=5）")
    else:
        print(f"❌ 阶段未正确更新，期望ID=5，实际ID={updated_opportunity['stage_id']}")
    
    if updated_opportunity['status'] == 1:
        print("✅ 状态已正确更新为'已赢单'（status=1）")
    else:
        print(f"❌ 状态未正确更新，期望status=1，实际status={updated_opportunity['status']}")
    
    if updated_opportunity['win_probability'] == 100:
        print("✅ 赢率已正确更新为100%")
    else:
        print(f"❌ 赢率未正确更新，期望100%，实际{updated_opportunity['win_probability']}%")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    test_mark_win_updates_stage()
