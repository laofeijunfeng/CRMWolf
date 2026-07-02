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
