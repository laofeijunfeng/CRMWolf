#!/usr/bin/env python3
"""测试 customer-follow-up PUT 端点修复"""

import asyncio
import httpx
from datetime import datetime

BASE_URL = "http://localhost:8000"

async def test_fix():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("=" * 60)
        print("测试 customer-follow-up PUT 端点修复")
        print("=" * 60)

        # 1. 获取管理员 token
        print("\n1. 获取管理员 token...")
        response = await client.post(f"{BASE_URL}/dev/create-admin", json={
            "name": "测试管理员",
            "email": "testadmin_fix@example.com"
        })

        if response.status_code != 200:
            print(f"❌ 获取 token 失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return

        token_data = response.json()
        token = token_data['access_token']
        print(f"✅ Token 获取成功: {token[:30]}...")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        # 2. 创建线索并转化为客户
        print("\n2. 创建测试客户...")
        test_lead = {
            "lead_name": "测试线索修复验证",
            "source": "线上注册",
            "city": "深圳",
            "contact_name": "测试联系人",
            "contact_phone": "13900139000",
            "company_scale": "51-200人"
        }
        response = await client.post(f"{BASE_URL}/api/v1/leads/", json=test_lead, headers=headers)

        if response.status_code != 201:
            print(f"❌ 线索创建失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return

        lead_data = response.json()
        lead_id = lead_data['id']
        print(f"✅ 线索创建成功，ID: {lead_id}")

        # 转化为客户
        convert_data = {
            "lead_id": lead_id,
            "account_name": "测试修复公司",
            "industry": "互联网",
            "address": "深圳市南山区"
        }
        response = await client.post(f"{BASE_URL}/api/v1/customers/convert-from-lead", json=convert_data, headers=headers)

        if response.status_code != 201:
            print(f"❌ 客户转化失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return

        customer_id = response.json()['customer_id']
        print(f"✅ 客户转化成功，ID: {customer_id}")

        # 3. 创建跟进记录
        print("\n3. 创建跟进记录...")
        follow_up_create = {
            "method": "电话",
            "content": "初步沟通，客户表示有意向",
            "next_follow_time": "2026-07-08T10:00:00",
            "next_action": "发送产品资料"
        }
        response = await client.post(f"{BASE_URL}/api/v1/customer-follow-ups/{customer_id}", json=follow_up_create, headers=headers)

        if response.status_code != 201:
            print(f"❌ 跟进记录创建失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return

        follow_up_data = response.json()
        follow_up_id = follow_up_data['id']
        print(f"✅ 跟进记录创建成功，ID: {follow_up_id}")
        print(f"   原始数据: {follow_up_data}")

        # 4. 测试 PUT 端点 - 模拟原始错误请求
        print("\n4. 测试 PUT 端点（原始错误请求格式）...")
        update_data = {
            "method": "微信",
            "content": "本来今天约了客户做线上交流，客户反馈因为其他会议耽误了，需要延期",
            "next_follow_time": "2026-07-10T00:00:00",
            "next_action": "确认交流时间"
        }
        response = await client.put(f"{BASE_URL}/api/v1/customer-follow-ups/{follow_up_id}", json=update_data, headers=headers)

        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            updated_data = response.json()
            print(f"✅ PUT 更新成功！")
            print(f"   更新后数据:")
            print(f"     - method: {updated_data['method']} (应为 '微信')")
            print(f"     - content: {updated_data['content'][:50]}... (应为新内容)")
            print(f"     - next_action: {updated_data['next_action']} (应为 '确认交流时间')")

            # 验证字段是否更新
            if updated_data['method'] == '微信' and '延期' in updated_data['content']:
                print("\n" + "=" * 60)
                print("🎉 修复验证成功！PUT 端点正常工作")
                print("=" * 60)
            else:
                print("\n⚠️  字段未正确更新，需要进一步检查")
        else:
            print(f"❌ PUT 更新失败")
            print(f"   响应: {response.text}")
            print("\n修复可能仍有问题，请检查实现")

        # 5. 测试部分更新（只更新 next_follow_time）
        print("\n5. 测试部分更新...")
        partial_update = {
            "next_follow_time": "2026-07-12T10:00:00"
        }
        response = await client.put(f"{BASE_URL}/api/v1/customer-follow-ups/{follow_up_id}", json=partial_update, headers=headers)

        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ 部分更新成功")
            print(f"   响应: {response.json()}")
        else:
            print(f"❌ 部分更新失败: {response.text}")

if __name__ == "__main__":
    asyncio.run(test_fix())