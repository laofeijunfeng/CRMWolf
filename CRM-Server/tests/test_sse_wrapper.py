"""
Tests for SSE Wrapper module.
"""

import json
from app.services.langgraph.sse_wrapper import build_waiting_for_user_event


def test_waiting_for_user_v2_fields():
    """测试 V2 SSE waiting_for_user 事件包含所有必需字段"""
    event = build_waiting_for_user_event(
        question="请选择目标客户",
        confirmationType="disambiguation",
        options=[
            {"id": 16, "name": "光大证券", "entity_info_inline": "ID:16 · 金融 · 活跃"}
        ],
        riskLevel="low",
        params={"action": "create_follow_up", "customer": "光大证券"}
    )

    data = json.loads(event.split("data: ")[1])

    assert data["confirmationType"] == "disambiguation"
    assert data["riskLevel"] == "low"
    assert data["params"]["action"] == "create_follow_up"
    assert len(data["options"]) == 1
    assert data["options"][0]["entity_info_inline"] == "ID:16 · 金融 · 活跃"