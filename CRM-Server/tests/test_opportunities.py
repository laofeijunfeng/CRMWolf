import httpx
import asyncio
import json

BASE_URL = "http://localhost:8000"


async def test_opportunities():
    print("获取管理员token...")
    response = await client.post(f"{BASE_URL}/dev/create-admin")
    print(f"获取token成功: {response.text[:50]}...")
    
    token_response = response.json()
    headers = {"Authorization": f"Bearer {token_response['token']}"}
    
    print("\n测试创建商机...")
    opportunity_data = {
        "opportunity_name": "XX公司私有化部署项目",
        "customer_id": 1,
        "expected_amount": 500000.00,
        "purchase_type": "NEW",
        "decision_maker_count": 3,
        "expected_closing_date": "2025-12-31",
        "stage_id": 1,
        "owner_id": "admin_open_id"
    }
    response = await client.post(f"{BASE_URL}/api/v1/opportunities/", json=opportunity_data, headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 201:
        opportunity = response.json()
        opportunity_id = opportunity['id']
        print(f"商机创建成功，ID: {opportunity_id}\n")
        
        print("测试查询商机列表...")
        response = await client.get(f"{BASE_URL}/api/v1/opportunities/", headers=headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:200]}...\n")
        
        print("测试查询商机详情...")
        response = await client.get(f"{BASE_URL}/api/v1/opportunities/{opportunity_id}", headers=headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:200]}...\n")
        
        print("测试推进商机阶段...")
        stage_update_data = {
            "stage_id": 2
        }
        response = await client.patch(f"{BASE_URL}/api/v1/opportunities/{opportunity_id}/stage", json=stage_update_data, headers=headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:200]}...\n")
        
        print("测试标记商机赢单...")
        win_data = {
            "actual_amount": 480000.00,
            "actual_closing_date": "2025-12-20"
        }
        response = await client.patch(f"{BASE_URL}/api/v1/opportunities/{opportunity_id}/win", json=win_data, headers=headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:200]}...\n")
        
        print("测试查询销售漏斗...")
        response = await client.get(f"{BASE_URL}/api/v1/analytics/sales-funnel?start_date=2025-01-01&end_date=2025-12-31", headers=headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:200]}...\n")
        
        print("测试查询阶段耗时分析...")
        response = await client.get(f"{BASE_URL}/api/v1/analytics/stage-duration?start_date=2025-01-01&end_date=2025-12-31", headers=headers)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text[:200]}...\n")
    else:
        print(f"商机创建失败: {response.text}\n")


async def main():
    global client, headers
    client = httpx.AsyncClient(timeout=30.0)
    
    try:
        await test_opportunities()
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
