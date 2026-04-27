"""
测试推进到100%赢率阶段自动标记赢单功能
"""
import requests
import json

BASE_URL = "http://localhost:8000"
TOKEN = "YOUR_TOKEN_HERE"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def test_auto_win_on_100_percent():
    """测试推进到100%赢率阶段是否自动标记为赢单"""
    
    # 1. 获取采购阶段列表，找到100%赢率的阶段
    opportunity_id = 12
    
    response = requests.get(
        f"{BASE_URL}/api/v1/opportunities/{opportunity_id}/procurement-stages",
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ 获取采购阶段失败: {response.status_code}")
        print(response.text)
        return
    
    stages = response.json()
    
    # 找到100%赢率的阶段
    stage_100 = None
    for stage in stages:
        if stage['win_probability'] == 100:
            stage_100 = stage
            break
    
    if not stage_100:
        print("❌ 没有找到100%赢率的阶段")
        return
    
    print(f"✅ 找到100%赢率阶段: {stage_100['stage_name']} (ID: {stage_100['id']})")
    
    # 2. 获取当前商机状态
    response = requests.get(
        f"{BASE_URL}/api/v1/opportunities/{opportunity_id}",
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ 获取商机详情失败: {response.status_code}")
        return
    
    opportunity = response.json()
    print(f"\n📊 当前商机状态:")
    print(f"   - 状态: {opportunity['status']} (0:跟进中, 1:已赢单, 2:已输单)")
    print(f"   - 当前阶段: {opportunity.get('current_stage_snapshot', {}).get('stage_name', 'N/A')}")
    print(f"   - 赢率: {opportunity['win_probability']}%")
    print(f"   - 实际成交金额: {opportunity.get('actual_amount', 'N/A')}")
    
    # 3. 推进到100%赢率阶段
    print(f"\n🚀 推进到100%赢率阶段: {stage_100['stage_name']}")
    
    response = requests.post(
        f"{BASE_URL}/api/v1/opportunities/{opportunity_id}/move-stage",
        headers=headers,
        json={"stage_template_id": stage_100['id']}
    )
    
    if response.status_code != 200:
        print(f"❌ 推进阶段失败: {response.status_code}")
        print(response.text)
        return
    
    result = response.json()
    
    # 4. 验证是否自动标记为赢单
    print(f"\n✅ 推进成功！验证结果:")
    print(f"   - 状态: {result['status']} (0:跟进中, 1:已赢单, 2:已输单)")
    print(f"   - 当前阶段: {result.get('current_stage_snapshot', {}).get('stage_name', 'N/A')}")
    print(f"   - 赢率: {result['win_probability']}%")
    print(f"   - 实际成交金额: {result.get('actual_amount', 'N/A')}")
    print(f"   - 实际成交日期: {result.get('actual_closing_date', 'N/A')}")
    
    # 验证
    if result['status'] == 1:
        print(f"\n🎉 测试通过！商机已自动标记为赢单")
        print(f"✅ 实际成交金额: {result.get('actual_amount')}")
        print(f"✅ 实际成交日期: {result.get('actual_closing_date')}")
        return True
    else:
        print(f"\n❌ 测试失败！商机未自动标记为赢单")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("测试推进到100%赢率阶段自动标记赢单功能")
    print("=" * 60)
    
    # 替换为有效的Token
    print("\n⚠️  请先在脚本中设置有效的 TOKEN")
    print("   TOKEN = 'your_valid_token_here'")
    print("\n或者使用以下命令测试：")
    print("   curl -X POST http://localhost:8000/api/v1/opportunities/12/move-stage \\")
    print('     -H "Authorization: Bearer YOUR_TOKEN" \\')
    print('     -H "Content-Type: application/json" \\')
    print('     -d \'{"stage_template_id": 5}\'  # 假设阶段5是100%赢率')
    print("=" * 60)
