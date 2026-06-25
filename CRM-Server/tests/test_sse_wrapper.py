"""
Tests for SSE Wrapper module.
"""

import json
from app.services.langgraph.sse_wrapper import (
    build_waiting_for_user_event,
    build_tool_call_event,
    build_tool_result_event,
)


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


def test_tool_call_v2_thinking_field():
    """测试 tool_call 事件包含 AI 推理过程"""
    event = build_tool_call_event(
        tool="search_customer",
        params={"keyword": "光大证券"},
        thinking="用户想跟进光大证券，需要先找到客户..."
    )

    data = json.loads(event.split("data: ")[1])

    assert data["tool"] == "search_customer"
    assert data["params"]["keyword"] == "光大证券"
    assert data["thinking"] == "用户想跟进光大证券，需要先找到客户..."


def test_tool_result_v2_summary_field():
    """测试 tool_result 事件包含业务化摘要"""
    event = build_tool_result_event(
        tool="search_customer",
        result={"count": 1, "customers": [{"name": "光大证券"}]},
        summary="找到 1 个客户：光大证券股份有限公司"
    )

    data = json.loads(event.split("data: ")[1])

    assert data["tool"] == "search_customer"
    assert data["result"]["count"] == 1
    assert data["summary"] == "找到 1 个客户：光大证券股份有限公司"