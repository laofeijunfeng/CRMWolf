import httpx

BASE_URL = "http://localhost:8000"

async def test_api():
    async with httpx.AsyncClient() as client:
        print("获取管理员token...")
        response = await client.post(f"{BASE_URL}/dev/create-admin", json={
            "name": "测试管理员",
            "email": "testadmin4@example.com"
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
            "lead_name": "测试线索8",
            "source": "线上注册",
            "city": "上海",
            "contact_name": "王五",
            "contact_phone": "13900139011",
            "company_scale": "51-200人"
        }
        response = await client.post(f"{BASE_URL}/api/v1/leads/", json=test_lead, headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 201:
            lead_data = response.json()
            lead_id = lead_data['id']
            print(f"线索创建成功，ID: {lead_id}\n")
            
            print("测试转化线索为客户...")
            convert_data = {
                "lead_id": lead_id,
                "account_name": "新王五科技有限公司",
                "industry": "互联网",
                "address": "上海市浦东新区"
            }
            response = await client.post(f"{BASE_URL}/api/v1/customers/convert-from-lead", json=convert_data, headers=headers)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}...\n")
            
            if response.status_code == 201:
                convert_result = response.json()
                customer_id = convert_result['customer_id']
                contact_id = convert_result['contact_id']
                print(f"转化成功！客户ID: {customer_id}, 联系人ID: {contact_id}\n")
                
                print("测试查询客户列表...")
                response = await client.get(f"{BASE_URL}/api/v1/customers/", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试查询客户详情...")
                response = await client.get(f"{BASE_URL}/api/v1/customers/{customer_id}", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试添加联系人...")
                new_contact = {
                    "name": "李六",
                    "gender": "1",
                    "position": "技术总监",
                    "is_decision_maker": False,
                    "mobile": "13900139008",
                    "email": "liuliu@example.com"
                }
                response = await client.post(f"{BASE_URL}/api/v1/customers/{customer_id}/contacts", json=new_contact, headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试更新客户状态为赢单...")
                status_data = {
                    "status": "1"
                }
                response = await client.patch(f"{BASE_URL}/api/v1/customers/{customer_id}/status", json=status_data, headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试查询统计...")
                response = await client.get(f"{BASE_URL}/api/v1/customers/statistics/summary", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text}")
        else:
            print(f"线索创建失败: {response.text}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api())
