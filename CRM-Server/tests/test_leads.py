import httpx

BASE_URL = "http://localhost:8000"

async def test_api():
    async with httpx.AsyncClient() as client:
        print("获取管理员token...")
        response = await client.post(f"{BASE_URL}/dev/create-admin", json={
            "name": "测试管理员",
            "email": "testadmin@example.com"
        })
        
        if response.status_code != 200:
            print(f"获取token失败: {response.text}")
            return
        
        token_data = response.json()
        token = token_data['access_token']
        print(f"获取token成功: {token[:30]}...\n")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        test_lead = {
            "lead_name": "Test Company 2",
            "source": "线上注册",
            "city": "Beijing",
            "contact_name": "Alice",
            "contact_phone": "13800138002",
            "company_scale": "51-200人"
        }
        
        print("测试创建线索...")
        response = await client.post(f"{BASE_URL}/api/v1/leads/", json=test_lead, headers=headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        
        if response.status_code == 201:
            lead_data = response.json()
            lead_id = lead_data['id']
            
            print("\n测试查询线索列表...")
            response = await client.get(f"{BASE_URL}/api/v1/leads/", headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}...")
            
            print(f"\n测试查询线索详情...")
            response = await client.get(f"{BASE_URL}/api/v1/leads/{lead_id}", headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}...")
            
            print(f"\n测试添加跟进记录...")
            follow_up = {
                "content": "已联系客户，表示有兴趣",
                "method": "电话",
                "next_follow_time": "2026-02-03T10:00:00"
            }
            response = await client.post(f"{BASE_URL}/api/v1/leads/{lead_id}/follow-ups", json=follow_up, headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}...")
            
            print(f"\n测试更新线索...")
            update_data = {
                "status": 1
            }
            response = await client.put(f"{BASE_URL}/api/v1/leads/{lead_id}", json=update_data, headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}...")
            
            print(f"\n测试查询统计...")
            response = await client.get(f"{BASE_URL}/api/v1/leads/statistics", headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api())
