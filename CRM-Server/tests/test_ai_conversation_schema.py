"""
Tests for ExecutionStepSchema V2 fields
"""
from app.schemas.ai_conversation import ExecutionStepSchema


def test_execution_step_v2_inline_fields():
    """测试 ExecutionStepSchema V2 inline 字段"""
    step_data = {
        "id": "step-001",
        "type": "tool_call",
        "title": "查找客户信息",
        "timestamp": "2026-06-25T10:30:01Z",
        "round": 1,
        "tool": "search_customer",
        "inline_text": "查找客户信息，找到 1 个客户：光大证券股份有限公司",
        "thinking": "用户想跟进光大证券...",
        "summary": "找到 1 个客户：光大证券股份有限公司"
    }

    step = ExecutionStepSchema(**step_data)

    assert step.inline_text == "查找客户信息，找到 1 个客户：光大证券股份有限公司"
    assert step.thinking == "用户想跟进光大证券..."
    assert step.summary == "找到 1 个客户：光大证券股份有限公司"


def test_execution_step_v2_progressive_disclosure():
    """测试 Progressive Disclosure 两层数据"""
    step_data = {
        "id": "step-002",
        "type": "waiting_for_user",
        "title": "创建跟进记录",
        "timestamp": "2026-06-25T10:30:02Z",
        "round": 2,
        "confirmationType": "confirmation",
        "riskLevel": "low",
        "summary_params": {"客户": "光大证券", "内容": "项目立项"},
        "detail_params": {
            "客户": {"value": "光大证券股份有限公司", "isEntity": True},
            "内容": {"value": "项目立项阶段，等待采购方式确认", "isEntity": False}
        }
    }

    step = ExecutionStepSchema(**step_data)

    assert step.confirmationType == "confirmation"
    assert step.riskLevel == "low"
    assert step.summary_params["客户"] == "光大证券"
    assert step.detail_params["客户"]["isEntity"] is True


def test_execution_step_v2_options_field():
    """测试 V2 options 字段（候选列表）"""
    step_data = {
        "id": "step-003",
        "type": "waiting_for_user",
        "title": "选择目标客户",
        "timestamp": "2026-06-25T10:30:03Z",
        "round": 1,
        "confirmationType": "disambiguation",
        "options": [
            {
                "id": 16,
                "name": "光大证券股份有限公司",
                "entity_info_inline": "ID:16 · 金融 · 活跃"
            },
            {
                "id": 17,
                "name": "光大证券投资",
                "entity_info_inline": "ID:17 · 金融 · 潜在"
            }
        ]
    }

    step = ExecutionStepSchema(**step_data)

    assert step.confirmationType == "disambiguation"
    assert len(step.options) == 2
    assert step.options[0]["name"] == "光大证券股份有限公司"
    assert step.options[0]["entity_info_inline"] == "ID:16 · 金融 · 活跃"


def test_execution_step_v2_backward_compatible():
    """测试 V2 字段向后兼容（所有新字段为 Optional）"""
    step_data = {
        "id": "step-004",
        "type": "tool_result",
        "title": "查询成功",
        "timestamp": "2026-06-25T10:30:04Z"
    }

    # 不提供任何 V2 字段，应该正常工作
    step = ExecutionStepSchema(**step_data)

    assert step.id == "step-004"
    assert step.type == "tool_result"  # use_enum_values = True 自动转换
    assert step.title == "查询成功"
    # V2 字段应该为 None
    assert step.inline_text is None
    assert step.thinking is None
    assert step.summary is None
    assert step.summary_params is None
    assert step.detail_params is None
    assert step.confirmationType is None
    assert step.riskLevel is None
    assert step.options is None