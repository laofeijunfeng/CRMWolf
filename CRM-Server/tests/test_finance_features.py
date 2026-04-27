import requests
from datetime import date, datetime, timedelta
import json

BASE_URL = "http://localhost:8000/api/v1"


def get_auth_token():
    """获取认证令牌"""
    print("🔐 登录获取认证令牌...")
    
    login_data = {
        "username": "admin",
        "password": "admin"
    }
    
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        print(f"✅ 登录成功，获取到令牌")
        return token
    else:
        print(f"❌ 登录失败: {response.text}")
        return None


def test_payment_confirmation():
    """测试回款确认功能"""
    print("\n" + "=" * 80)
    print("测试1: 回款确认功能")
    print("=" * 80)
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(f"{BASE_URL}/payments/payment-records", headers=headers)
    
    if response.status_code != 200:
        print(f"❌ 获取回款记录失败: {response.text}")
        return False
    
    records = response.json()
    
    pending_records = [r for r in records if r.get("confirmation_status") == "PENDING"]
    
    if not pending_records:
        print("ℹ️  没有待确认的回款记录，跳过此测试")
        return True
    
    test_record = pending_records[0]
    record_id = test_record["id"]
    
    print(f"📝 测试回款记录ID: {record_id}")
    print(f"   回款金额: {test_record['actual_amount']}")
    print(f"   回款日期: {test_record['payment_date']}")
    
    confirm_data = {
        "action": "confirm",
        "notes": "财务审核通过，确认入账"
    }
    
    response = requests.post(
        f"{BASE_URL}/finance/payment-records/{record_id}/confirm",
        json=confirm_data,
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 回款确认成功")
        print(f"   确认状态: {result['confirmation_status']}")
        print(f"   确认人: {result.get('confirmed_by_name')}")
        print(f"   确认时间: {result.get('confirmed_time')}")
        return True
    else:
        print(f"❌ 回款确认失败: {response.text}")
        return False


def test_aging_analysis():
    """测试应收账款账龄分析"""
    print("\n" + "=" * 80)
    print("测试2: 应收账款账龄分析")
    print("=" * 80)
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/finance/receivables/aging-analysis",
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 获取账龄分析成功")
        
        summary = result["summary"]
        print(f"\n📊 总体概况:")
        print(f"   总逾期金额: {summary['total_overdue_amount']:.2f} 元")
        print(f"   逾期计划数: {summary['total_overdue_plans']}")
        print(f"   分析日期: {summary['analysis_date']}")
        
        print(f"\n📈 账龄分析:")
        for bucket in result["aging_analysis"]:
            print(f"   {bucket['range']}: {bucket['amount']:.2f} 元 ({bucket['count']} 笔)")
        
        if result["details"]:
            print(f"\n📋 逾期明细（前5条）:")
            for detail in result["details"][:5]:
                print(f"   - {detail['contract_name']}: {detail['remaining_amount']:.2f} 元, 逾期 {detail['days_overdue']} 天")
        
        return True
    else:
        print(f"❌ 获取账龄分析失败: {response.text}")
        return False


def test_overdue_alerts():
    """测试逾期预警列表"""
    print("\n" + "=" * 80)
    print("测试3: 逾期预警列表")
    print("=" * 80)
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/finance/receivables/overdue-alerts",
        headers=headers,
        params={"limit": 10}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 获取逾期预警成功")
        print(f"   总记录数: {result['total']}")
        print(f"   返回记录: {len(result['items'])} 条")
        
        if result["items"]:
            print(f"\n⚠️  逾期预警明细:")
            for alert in result["items"][:5]:
                print(f"   - {alert['contract_name']} ({alert['customer_name']})")
                print(f"     阶段: {alert['stage_name']}")
                print(f"     欠款: {alert['remaining_amount']:.2f} 元")
                print(f"     逾期: {alert['days_overdue']} 天")
                print(f"     负责人: {alert.get('owner_name', 'N/A')}")
        
        return True
    else:
        print(f"❌ 获取逾期预警失败: {response.text}")
        return False


def test_revenue_report():
    """测试合同收入报表"""
    print("\n" + "=" * 80)
    print("测试4: 合同收入统计报表")
    print("=" * 80)
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    end_date = date.today()
    start_date = end_date - timedelta(days=90)
    
    for group_by in ["month", "customer"]:
        print(f"\n📊 按 {group_by} 分组统计:")
        
        response = requests.get(
            f"{BASE_URL}/finance/reports/contract-revenue",
            headers=headers,
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "group_by": group_by
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 获取报表成功（按 {group_by} 分组）")
            
            if group_by == "month":
                for item in result["data"][:5]:
                    print(f"   {item['period']}: 合同 {item['contract_count']} 个, 总额 {item['total_amount']:.2f} 元, 实收 {item['total_paid']:.2f} 元, 欠款 {item['total_pending']:.2f} 元")
            else:
                for item in result["data"][:5]:
                    print(f"   {item['customer_name']}: 合同 {item['contract_count']} 个, 总额 {item['total_amount']:.2f} 元, 实收 {item['total_paid']:.2f} 元, 欠款 {item['total_pending']:.2f} 元")
        else:
            print(f"❌ 获取报表失败: {response.text}")
            return False
    
    return True


def test_pending_confirmations():
    """测试待确认回款列表"""
    print("\n" + "=" * 80)
    print("测试5: 待确认回款列表")
    print("=" * 80)
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/finance/pending-confirmations",
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ 获取待确认回款列表成功")
        print(f"   总待确认数: {result['total']}")
        print(f"   返回记录: {len(result['items'])} 条")
        
        if result["items"]:
            print(f"\n📝 待确认回款明细:")
            for item in result["items"][:5]:
                print(f"   - 回款ID: {item['id']}")
                print(f"     合同: {item.get('contract_name', 'N/A')}")
                print(f"     阶段: {item.get('stage_name', 'N/A')}")
                print(f"     金额: {item['actual_amount']:.2f} 元")
                print(f"     回款日期: {item['payment_date']}")
                print(f"     登记人: {item.get('creator_name', 'N/A')}")
        
        return True
    else:
        print(f"❌ 获取待确认回款列表失败: {response.text}")
        return False


def main():
    """运行所有测试"""
    print("=" * 80)
    print("飞书轻量化CRM系统 - 财务功能测试")
    print("=" * 80)
    
    tests = [
        ("回款确认功能", test_payment_confirmation),
        ("应收账款账龄分析", test_aging_analysis),
        ("逾期预警列表", test_overdue_alerts),
        ("合同收入报表", test_revenue_report),
        ("待确认回款列表", test_pending_confirmations)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ 测试 '{test_name}' 发生异常: {str(e)}")
            results.append((test_name, False))
    
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} - {test_name}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    print("=" * 80)


if __name__ == "__main__":
    main()
