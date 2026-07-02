import pytest
from app.services.approval_ai_parser import PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE

def test_prompt_format_no_keyerror():
    """Test that template formatting doesn't raise KeyError."""
    current_date = "2026-07-02"
    prompt = PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date=current_date)
    assert "今天是 2026-07-02" in prompt
    assert "{{" not in prompt  # 双花括号应被 format 转为单花括号
    assert '"flow"' in prompt  # JSON 结构应存在

def test_prompt_contains_json_example():
    """Test that formatted prompt contains valid JSON structure."""
    prompt = PARSE_APPROVAL_SYSTEM_PROMPT_TEMPLATE.format(current_date="2026-07-02")
    assert '"flow_name"' in prompt
    assert '"node_name"' in prompt
    assert '"approve_role"' in prompt


def test_parsed_event_serialization():
    """parsed 事件应能被 json 直接序列化（依赖 to_sse_dict，Task 2 已实现）。"""
    import json

    from app.schemas.approval_ai import ApprovalAIParsedFlow, ApprovalAIParsedNode

    flow = ApprovalAIParsedFlow(
        flow_name="测试",
        flow_code="TEST",
        min_amount=100000.0,
        max_amount=500000.0,
        nodes=[
            ApprovalAIParsedNode(
                node_name="测试节点",
                node_code="TEST",
                node_order=1,
                approve_role="SALES_DIRECTOR",
            )
        ],
    )

    # 模拟 parser yield 的 parsed 事件结构
    event = {
        "event": "parsed",
        "flow": flow.to_sse_dict(),
        "thinking_process": "测试思考过程",
    }

    json_str = json.dumps(event)
    assert json_str is not None
    assert '"event": "parsed"' in json_str
