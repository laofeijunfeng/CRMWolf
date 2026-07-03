"""Approval AI 接口层稳定性测试：SSEJsonEncoder + done 事件 + 三层错误处理。"""
import json

import pytest

from app.api import approval_ai as approval_ai_module
from app.api.approval_ai import parse_approval_flow
from app.schemas.approval_ai import ApprovalAIParseRequest


def test_sse_json_encoder_used():
    """SSEJsonEncoder 可导入：处理 LangChain BaseMessage，普通 dict 正常序列化。"""
    from langchain_core.messages import HumanMessage

    from app.services.langgraph.sse_wrapper import SSEJsonEncoder

    assert isinstance(SSEJsonEncoder(), json.JSONEncoder)

    # 普通 dict（审批 AI 事件的真实形态）应可直接序列化
    payload = {"event": "parsed", "flow": {"min_amount": 100000.0, "max_amount": None}}
    json.dumps(payload, cls=SSEJsonEncoder)  # 不抛异常

    # BaseMessage（SSEJsonEncoder 的核心职责）应被转为可序列化 dict
    msg = HumanMessage(content="你好")
    json_str = json.dumps({"message": msg}, cls=SSEJsonEncoder, ensure_ascii=False)
    assert "你好" in json_str


async def test_sse_stream_ends_with_done_event(monkeypatch):
    """SSE 流始终以 done 事件结束（成功路径，success=True）。"""
    # mock parser service：yield status + parsed
    async def fake_stream(db, user_message, team_id):
        yield {"event": "status", "message": "正在分析..."}
        yield {"event": "parsed", "flow": {"flow_name": "测试"}, "thinking_process": "..."}

    monkeypatch.setattr(
        approval_ai_module.approval_ai_parser_service,
        "parse_approval_flow_stream",
        fake_stream,
    )

    # mock SessionLocal 避免真实 DB 连接
    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(approval_ai_module, "SessionLocal", lambda: FakeSession())

    resp = await parse_approval_flow(
        ApprovalAIParseRequest(content="测试"),
        current_user=object(),
        team_id=1,
    )

    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
    body = "".join(chunks)

    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    assert data_lines, "SSE 流应至少产生数据行"
    # done 必须是最后一个 data 事件
    assert '"event": "done"' in data_lines[-1]
    # parsed 事件后 success 应为 True
    done_payload = json.loads(data_lines[-1][len("data: "):])
    assert done_payload["event"] == "done"
    assert done_payload["success"] is True


async def test_sse_stream_emits_done_on_parser_exception(monkeypatch):
    """parser service 抛异常时，SSE 流仍以 done 事件结束（success=False）。"""
    async def broken_stream(db, user_message, team_id):
        yield {"event": "status", "message": "正在分析..."}
        raise RuntimeError("upstream blew up")
        yield  # pragma: no cover  - 让它成为 async generator

    monkeypatch.setattr(
        approval_ai_module.approval_ai_parser_service,
        "parse_approval_flow_stream",
        broken_stream,
    )

    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(approval_ai_module, "SessionLocal", lambda: FakeSession())

    resp = await parse_approval_flow(
        ApprovalAIParseRequest(content="测试"),
        current_user=object(),
        team_id=1,
    )

    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
    body = "".join(chunks)

    data_lines = [line for line in body.splitlines() if line.startswith("data: ")]
    # 应有 error 事件 + 末尾 done（success=False）
    events = [json.loads(line[len("data: "):]) for line in data_lines]
    event_types = [e.get("event") for e in events]
    assert "error" in event_types
    assert event_types[-1] == "done"
    done_payload = events[-1]
    assert done_payload["success"] is False
