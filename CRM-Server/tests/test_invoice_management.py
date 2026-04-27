import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1"


def get_auth_token():
    """获取认证token"""
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
        return response.json().get("access_token")
    return None


def test_invoice_management():
    """发票管理模块测试"""
    print("=" * 80)
    print("飞书轻量化CRM系统 - 发票管理模块测试")
    print("=" * 80)
    
    token = get_auth_token()
    if not token:
        print("❌ 登录失败，无法获取认证令牌")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 获取测试数据
    print("\n📋 获取测试数据...")
    response = requests.get(f"{BASE_URL}/customers", headers=headers)
    if response.status_code != 200 or not response.json():
        print("❌ 没有可用的客户数据，请先创建客户")
        return
    
    customers = response.json()
    customer_id = customers[0]['id']
    print(f"✅ 使用客户ID: {customer_id}, 客户名称: {customers[0]['account_name']}")
    
    response = requests.get(f"{BASE_URL}/contracts", headers=headers)
    if response.status_code != 200 or not response.json():
        print("❌ 没有可用的合同数据，请先创建合同")
        return
    
    contracts = response.json()
    contract_id = contracts[0]['id']
    print(f"✅ 使用合同ID: {contract_id}, 合同名称: {contracts[0]['contract_name']}")
    
    response = requests.get(f"{BASE_URL}/payments/payment-plans", headers=headers)
    if response.status_code != 200 or not response.json()['items']:
        print("❌ 没有可用的回款计划数据，请先创建回款计划")
        return
    
    payment_plans = response.json()['items']
    payment_plan_id = payment_plans[0]['id']
    print(f"✅ 使用回款计划ID: {payment_plan_id}, 阶段名称: {payment_plans[0]['stage_name']}")
    
    invoice_title_id = None
    invoice_application_id = None
    
    try:
        # 测试1: 创建开票抬头
        print("\n" + "=" * 80)
        print("测试1: 创建开票抬头")
        print("=" * 80)
        
        title_data = {
            "title_type": "COMPANY",
            "title": "测试公司开票抬头",
            "taxpayer_id": "91110000MA00000001",
            "bank_name": "中国银行北京分行",
            "bank_account": "1234567890",
            "address": "北京市朝阳区测试路123号",
            "phone": "010-12345678"
        }
        
        response = requests.post(
            f"{BASE_URL}/invoice-titles?customer_id={customer_id}",
            json=title_data,
            headers=headers
        )
        
        if response.status_code == 200:
            title = response.json()
            invoice_title_id = title['id']
            print(f"✅ 创建开票抬头成功")
            print(f"   抬头ID: {title['id']}")
            print(f"   抬头名称: {title['title']}")
            print(f"   纳税人识别号: {title['taxpayer_id']}")
        else:
            print(f"❌ 创建开票抬头失败: {response.text}")
            return
        
        # 测试2: 查询开票抬头列表
        print("\n" + "=" * 80)
        print("测试2: 查询开票抬头列表")
        print("=" * 80)
        
        response = requests.get(
            f"{BASE_URL}/invoice-titles?customer_id={customer_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            titles = result['invoice_titles']
            print(f"✅ 查询成功，共 {len(titles)} 个开票抬头")
            if titles:
                print(f"   第一个抬头: {titles[0]['title']}")
        else:
            print(f"❌ 查询失败: {response.text}")
        
        # 测试3: 设置默认抬头
        print("\n" + "=" * 80)
        print("测试3: 设置默认抬头")
        print("=" * 80)
        
        response = requests.patch(
            f"{BASE_URL}/invoice-titles/{invoice_title_id}/set-default",
            headers=headers
        )
        
        if response.status_code == 200:
            title = response.json()
            print(f"✅ 设置默认抬头成功")
            print(f"   抬头ID: {title['id']}")
            print(f"   是否默认: {title['is_default']}")
        else:
            print(f"❌ 设置默认抬头失败: {response.text}")
        
        # 测试4: 创建发票申请
        print("\n" + "=" * 80)
        print("测试4: 创建发票申请")
        print("=" * 80)
        
        application_data = {
            "payment_plan_id": payment_plan_id,
            "invoice_title_id": invoice_title_id,
            "invoice_amount": 75000.00,
            "invoice_type": "VAT_SPECIAL"
        }
        
        response = requests.post(
            f"{BASE_URL}/invoice-applications",
            json=application_data,
            headers=headers
        )
        
        if response.status_code == 200:
            application = response.json()
            invoice_application_id = application['id']
            print(f"✅ 创建发票申请成功")
            print(f"   申请ID: {application['id']}")
            print(f"   申请单号: {application['application_number']}")
            print(f"   开票金额: {application['invoice_amount']}")
            print(f"   发票类型: {application['invoice_type']}")
            print(f"   状态: {application['status']}")
            print(f"   客户名称: {application['customer_name']}")
            print(f"   合同名称: {application['contract_name']}")
        else:
            print(f"❌ 创建发票申请失败: {response.text}")
            return
        
        # 测试5: 查询发票申请列表
        print("\n" + "=" * 80)
        print("测试5: 查询发票申请列表")
        print("=" * 80)
        
        response = requests.get(
            f"{BASE_URL}/invoice-applications",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            applications = result['invoice_applications']
            print(f"✅ 查询成功，共 {len(applications)} 个发票申请")
            if applications:
                print(f"   第一个申请单号: {applications[0]['application_number']}")
        else:
            print(f"❌ 查询失败: {response.text}")
        
        # 测试6: 查询发票申请详情
        print("\n" + "=" * 80)
        print("测试6: 查询发票申请详情")
        print("=" * 80)
        
        response = requests.get(
            f"{BASE_URL}/invoice-applications/{invoice_application_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            application = response.json()
            print(f"✅ 查询成功")
            print(f"   申请单号: {application['application_number']}")
            print(f"   开票抬头: {application['invoice_title_title']}")
            print(f"   回款计划阶段: {application['payment_plan_stage_name']}")
        else:
            print(f"❌ 查询失败: {response.text}")
        
        # 测试7: 提交审批
        print("\n" + "=" * 80)
        print("测试7: 提交发票申请审批")
        print("=" * 80)
        
        response = requests.post(
            f"{BASE_URL}/invoice-applications/{invoice_application_id}/submit",
            headers=headers
        )
        
        if response.status_code == 200:
            application = response.json()
            print(f"✅ 提交审批成功")
            print(f"   当前状态: {application['status']}")
        else:
            print(f"❌ 提交审批失败: {response.text}")
        
        # 测试8: 财务审批
        print("\n" + "=" * 80)
        print("测试8: 财务审批发票申请")
        print("=" * 80)
        
        review_data = {
            "action": "approve",
            "comment": "审批通过，请及时开票"
        }
        
        response = requests.post(
            f"{BASE_URL}/invoice-applications/{invoice_application_id}/review",
            json=review_data,
            headers=headers
        )
        
        if response.status_code == 200:
            application = response.json()
            print(f"✅ 审批成功")
            print(f"   当前状态: {application['status']}")
            print(f"   审批意见: {application['review_comment']}")
        else:
            print(f"❌ 审批失败: {response.text}")
        
        # 测试9: 标记为已开票
        print("\n" + "=" * 80)
        print("测试9: 标记为已开票")
        print("=" * 80)
        
        response = requests.post(
            f"{BASE_URL}/invoice-applications/{invoice_application_id}/mark-issued",
            headers=headers
        )
        
        if response.status_code == 200:
            application = response.json()
            print(f"✅ 标记成功")
            print(f"   当前状态: {application['status']}")
        else:
            print(f"❌ 标记失败: {response.text}")
        
        # 测试10: 查询回款计划关联发票
        print("\n" + "=" * 80)
        print("测试10: 查询回款计划关联发票")
        print("=" * 80)
        
        response = requests.get(
            f"{BASE_URL}/invoice-applications/payment-plans/{payment_plan_id}/invoices",
            headers=headers
        )
        
        if response.status_code == 200:
            summary = response.json()
            print(f"✅ 查询成功")
            print(f"   回款计划ID: {summary['payment_plan_id']}")
            print(f"   阶段名称: {summary['stage_name']}")
            print(f"   计划金额: {summary['planned_amount']}")
            print(f"   已开票总金额: {summary['total_invoiced_amount']}")
            print(f"   发票数量: {summary['invoice_count']}")
        else:
            print(f"❌ 查询失败: {response.text}")
        
        print("\n" + "=" * 80)
        print("✅ 发票管理模块测试完成！")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_invoice_management()
