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


async def test_http_error_event_has_recovery_hint(monkeypatch):
    """HTTP 错误路径：parser yield 的 error 事件必须包含 recovery + detail（Task 5 契约）。"""
    import httpx
    from unittest.mock import AsyncMock, MagicMock

    from app.crud import ai_config
    from app.services import approval_ai_parser as parser_module
    from app.services.approval_ai_parser import approval_ai_parser_service

    # mock AI 配置
    monkeypatch.setattr(
        ai_config.ai_config_crud, "get_config",
        lambda db, tid: MagicMock(api_host="http://x", model_name="m"),
    )
    monkeypatch.setattr(
        ai_config.ai_config_crud, "get_decrypted_api_key", lambda db, tid: "key",
    )

    # mock httpx：raise_for_status 抛 HTTPStatusError
    fake_response = MagicMock()
    fake_response.status_code = 400
    fake_response.text = "Bad request"

    def raise_for_status():
        raise httpx.HTTPStatusError("400", request=MagicMock(), response=fake_response)

    fake_response.raise_for_status = raise_for_status

    stream_cm = AsyncMock()
    stream_cm.__aenter__.return_value = fake_response
    stream_cm.__aexit__.return_value = False

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False
    # stream(...) 必须同步返回 async CM（不能是 coroutine）
    fake_client.stream = MagicMock(return_value=stream_cm)

    monkeypatch.setattr(parser_module.httpx, "AsyncClient", lambda *a, **k: fake_client)

    events = []
    async for ev in approval_ai_parser_service.parse_approval_flow_stream(
        db=None, user_message="test", team_id=1
    ):
        events.append(ev)

    errs = [e for e in events if e.get("event") == "error"]
    assert errs, "HTTP 错误应产生 error 事件"
    assert "recovery" in errs[0] and errs[0]["recovery"]
    assert "detail" in errs[0] and errs[0]["detail"]
    assert "400" in errs[0]["message"]
