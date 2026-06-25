"""
Tests for LangGraph state definitions.
"""

from typing import Dict, Any

from app.services.langgraph.state import EntityCandidate


def test_entity_candidate_v2_fields():
    """测试 EntityCandidate V2 字段完整性"""
    candidate: EntityCandidate = {
        "id": 16,
        "name": "光大证券股份有限公司",
        "hint": "金融行业客户",
        "matched_by": "name",
        "entity_type": "customer",
        "industry": "金融",
        "status": "活跃",
        "amount": None,
        "stage": None,
        "entity_info_inline": "ID:16 · 金融 · 活跃",
        "entity_info_detail": {
            "industry": "金融服务业",
            "status": "活跃",
            "address": "上海市静安区"
        }
    }

    assert candidate["industry"] == "金融"
    assert candidate["status"] == "活跃"
    assert candidate["entity_info_inline"] == "ID:16 · 金融 · 活跃"
    assert candidate["entity_info_detail"]["address"] == "上海市静安区"