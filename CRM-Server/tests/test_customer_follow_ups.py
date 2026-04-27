import httpx

BASE_URL = "http://localhost:8000"

async def test_api():
    async with httpx.AsyncClient() as client:
        print("获取管理员token...")
        response = await client.post(f"{BASE_URL}/dev/create-admin", json={
            "name": "测试管理员",
            "email": "testadmin5@example.com"
        })
        
        if response.status_code != 200:
            print(f"获取token失败，响应: {response.text}")
            print("尝试使用已有用户登录...")
            response = await client.post(f"{BASE_URL}/dev/create-admin", json={
                "name": "Admin User",
                "email": "admin@example.com"
            })
            if response.status_code != 200:
                print("登录失败")
                return
        
        token_data = response.json()
        token = token_data['access_token']
        print(f"获取token成功: {token[:30]}...\n")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        print("测试创建线索...")
        test_lead = {
            "lead_name": "测试线索9",
            "source": "线上注册",
            "city": "深圳",
            "contact_name": "赵六",
            "contact_phone": "13900139012",
            "company_scale": "51-200人"
        }
        response = await client.post(f"{BASE_URL}/api/v1/leads/", json=test_lead, headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 201:
            lead_data = response.json()
            lead_id = lead_data['id']
            print(f"线索创建成功，ID: {lead_id}\n")
            
            print("测试添加线索跟进记录...")
            follow_up = {
                "content": "已联系客户，表示有兴趣",
                "method": "电话",
                "nextFollowTime": "2026-02-04T10:00:00"
            }
            response = await client.post(f"{BASE_URL}/api/v1/leads/{lead_id}/follow-ups", json=follow_up, headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}...\n")
            
            print("测试转化线索为客户...")
            convert_data = {
                "lead_id": lead_id,
                "account_name": "新赵六科技有限公司",
                "industry": "互联网",
                "address": "深圳市南山区"
            }
            response = await client.post(f"{BASE_URL}/api/v1/customers/convert-from-lead", json=convert_data, headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}...\n")
            
            if response.status_code == 201:
                convert_result = response.json()
                customer_id = convert_result['customer_id']
                print(f"转化成功！客户ID: {customer_id}\n")
                
                print("测试查询客户跟进列表...")
                response = await client.get(f"{BASE_URL}/api/v1/customer-follow-ups/{customer_id}", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试为客户添加跟进记录...")
                customer_follow_up = {
                    "content": "与客户技术负责人深入沟通，他们对我们的产品很感兴趣",
                    "method": "电话",
                    "nextFollowTime": "2026-02-05T10:00:00"
                }
                response = await client.post(f"{BASE_URL}/api/v1/customer-follow-ups/{customer_id}", json=customer_follow_up, headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                if response.status_code == 201:
                    follow_up_data = response.json()
                    follow_up_id = follow_up_data['id']
                    print(f"跟进记录创建成功，ID: {follow_up_id}\n")
                    
                    print("测试更新下次跟进时间...")
                    update_data = {
                        "nextFollowTime": "2026-02-06T10:00:00"
                    }
                    response = await client.patch(f"{BASE_URL}/api/v1/customer-follow-ups/{follow_up_id}/next-time", json=update_data, headers=headers)
                    print(f"状态码: {response.status_code}")
                    print(f"响应: {response.text[:200]}...\n")
        else:
            print(f"线索创建失败: {response.text}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api())
