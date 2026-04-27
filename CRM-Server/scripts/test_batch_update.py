#!/usr/bin/env python3
"""
测试采购方式批量更新接口
"""
import requests
import json

BASE_URL = "http://localhost:8000/api/v1"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMiIsImV4cCI6MTc3MDk3NDA4MH0.2uvG52zg13nYp96r5nwB-it2CFL1KVGuAolqiDSs0pE"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}


def test_batch_update_stages():
    """测试批量更新阶段接口"""
    url = f"{BASE_URL}/procurement-methods/2/stages"
    
    # 请求体：更新采购方式ID=2的阶段
    payload = {
        "stages": [
            # 更新现有阶段（有ID）
            {
                "id": 9,
                "template_code": "PRE_QUAL",
                "stage_name": "资格预审（更新）",
                "win_probability": 25,
                "sort_order": 1,
                "is_default_start": 1,
                "can_skip": 0,
                "description": "第一阶段：提交资格预审文件"
            },
            # 更新现有阶段
            {
                "id": 10,
                "template_code": "BID_EVAL",
                "stage_name": "投标评审（更新）",
                "win_probability": 55,
                "sort_order": 2,
                "is_default_start": 0,
                "can_skip": 0,
                "description": "第二阶段：技术标和商务标评审"
            },
            # 新增阶段（无ID）
            {
                "id": None,
                "template_code": "BID_OPEN",
                "stage_name": "开标评标",
                "win_probability": 75,
                "sort_order": 3,
                "is_default_start": 0,
                "can_skip": 0,
                "description": "第三阶段：公开开标并评标"
            }
        ]
    }
    
    print(f"\n{'='*80}")
    print("测试批量更新阶段接口")
    print(f"{'='*80}")
    print(f"URL: PUT {url}")
    print(f"\n请求体：")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    try:
        response = requests.put(url, json=payload, headers=headers)
        
        print(f"\n响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ 批量更新成功！")
            print(f"返回了 {len(result)} 个阶段：")
            for stage in result:
                print(f"  - {stage['stage_name']} (ID: {stage['id']})")
        else:
            print(f"\n❌ 请求失败！")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"\n❌ 请求异常: {e}")


def test_full_update():
    """测试完整更新接口（方式+阶段）"""
    url = f"{BASE_URL}/procurement-methods/2/full"
    
    payload = {
        "method": {
            "name": "公开招标（更新）",
            "description": "向所有潜在供应商发出的公开招标采购流程（已更新）",
            "is_active": 1,
            "sort_order": 2
        },
        "stages": [
            # 删除阶段（有ID + mark_delete=true）
            {
                "id": 12,
                "mark_delete": True
            },
            # 更新现有阶段
            {
                "id": 9,
                "template_code": "PRE_QUAL",
                "stage_name": "资格预审（最终版）",
                "win_probability": 20,
                "sort_order": 1,
                "is_default_start": 1,
                "can_skip": 0,
                "description": "提交资格预审文件"
            }
        ]
    }
    
    print(f"\n{'='*80}")
    print("测试完整更新接口（方式+阶段）")
    print(f"{'='*80}")
    print(f"URL: PUT {url}")
    print(f"\n请求体：")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    try:
        response = requests.put(url, json=payload, headers=headers)
        
        print(f"\n响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ 完整更新成功！")
            print(f"\n采购方式信息：")
            print(f"  - ID: {result['id']}")
            print(f"  - 名称: {result['name']}")
            print(f"  - 描述: {result['description']}")
            print(f"\n阶段模板（{len(result['stage_templates'])}个）：")
            for stage in result['stage_templates']:
                print(f"  - {stage['stage_name']} (ID: {stage['id']}, 赢率: {stage['win_probability']}%)")
        else:
            print(f"\n❌ 请求失败！")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"\n❌ 请求异常: {e}")


if __name__ == "__main__":
    print("="*80)
    print("采购方式批量更新接口测试")
    print("="*80)
    
    # 测试批量更新阶段
    test_batch_update_stages()
    
    # 测试完整更新
    # test_full_update()
    
    print(f"\n{'='*80}")
    print("测试完成！")
    print("="*80)
