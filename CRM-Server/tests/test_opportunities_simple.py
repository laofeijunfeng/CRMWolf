import httpx
import json

BASE_URL = "http://localhost:8000"


def test_opportunities():
    client = httpx.Client(timeout=30.0)
    
    print("获取管理员token...")
    response = client.post(f"{BASE_URL}/dev/create-admin", json={
        "name": "test",
        "email": "test@example.com",
        "region": "北京"
    })
    print(f"获取token成功: {response.text[:100]}...")
    
    token_response = response.json()
    headers = {"Authorization": f"Bearer {token_response['access_token']}"}
    
    print("\n测试查询销售阶段列表...")
    response = client.get(f"{BASE_URL}/api/v1/opportunities/stages", headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        stages = response.json()
        print(f"销售阶段数量: {len(stages)}")
        if len(stages) > 0:
            stage_id = stages[0]['id']
            print(f"使用第一个阶段 ID: {stage_id}\n")
            
            print("测试创建商机...")
            opportunity_data = {
                "opportunity_name": "XX公司私有化部署项目",
                "customer_id": 1,
                "expected_amount": 500000.00,
                "purchase_type": "NEW",
                "decision_maker_count": 3,
                "expected_closing_date": "2025-12-31",
                "stage_id": stage_id,
                "owner_id": "admin_open_id"
            }
            response = client.post(f"{BASE_URL}/api/v1/opportunities/", json=opportunity_data, headers=headers)
            print(f"状态码: {response.status_code}")
            if response.status_code == 201:
                opportunity = response.json()
                opportunity_id = opportunity['id']
                print(f"商机创建成功，ID: {opportunity_id}\n")
                
                print("测试查询商机列表...")
                response = client.get(f"{BASE_URL}/api/v1/opportunities/", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试查询商机详情...")
                response = client.get(f"{BASE_URL}/api/v1/opportunities/{opportunity_id}", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试推进商机阶段...")
                stage_update_data = {
                    "stage_id": 2
                }
                response = client.patch(f"{BASE_URL}/api/v1/opportunities/{opportunity_id}/stage", json=stage_update_data, headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试标记商机赢单...")
                win_data = {
                    "actual_amount": 480000.00,
                    "actual_closing_date": "2025-12-20"
                }
                response = client.patch(f"{BASE_URL}/api/v1/opportunities/{opportunity_id}/win", json=win_data, headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试查询销售漏斗...")
                response = client.get(f"{BASE_URL}/api/v1/analytics/sales-funnel?start_date=2025-01-01&end_date=2025-12-31", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
                
                print("测试查询阶段耗时分析...")
                response = client.get(f"{BASE_URL}/api/v1/analytics/stage-duration?start_date=2025-01-01&end_date=2025-12-31", headers=headers)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}...\n")
            else:
                print(f"商机创建失败: {response.text}\n")
        else:
            print(f"获取销售阶段列表失败: {response.text}\n")
    else:
        print(f"获取token失败: {response.text}\n")
    
    client.close()


if __name__ == "__main__":
    test_opportunities()
