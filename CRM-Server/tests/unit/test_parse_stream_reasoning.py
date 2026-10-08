"""parse_stream 对 reasoning 模型输出的健壮性回归测试。"""
import asyncio
import json
from typing import Any

import pytest

from app.services.ai_parser.base_parser import EntityAIParserBase


class _StubParser(EntityAIParserBase):
    """只测基类的 SSE 累积与 JSON 解析，不发真实请求。"""

    entity_type = "lead"

    def get_system_prompt(self, db=None, team_id=None):  # noqa: ARG002
        return "stub"

    def get_enum_maps(self):
        return {}

    def parse_ai_response(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return parsed

    async def create_entity(self, db, parsed_data, user_id, team_id):  # noqa: ARG002
        raise NotImplementedError

    async def post_create_actions(self, db, entity, parsed_data, user_id, team_id):  # noqa: ARG002
        return None


def _sse_line(delta: dict[str, Any]) -> str:
    chunk = {"choices": [{"delta": delta}]}
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


@pytest.mark.parametrize(
    "raw_stream,expect_event,expect_keyword",
    [
        # reasoning 模型：思考 chunk + 正常 content → parsed
        (
            _sse_line({"reasoning_content": "思考过程"}) + _sse_line({"content": '{"lead_info": {}}'}),
            "parsed",
            None,
        ),
        # reasoning 耗尽 token：content 一个字没有 → 明确的"输出为空"错误
        (_sse_line({"reasoning_content": "全部预算被思考耗尽"}), "error", "输出为空"),
        # content 截断：JSON 不完整 → 明确的"被截断"错误，而非 char 0
        (_sse_line({"content": '{"lead_info": "unterminated'}), "error", "截断"),
        # 空串 → 同样是输出为空
        (_sse_line({"content": ""}), "error", "输出为空"),
    ],
)
def test_parse_stream_handles_reasoning_model_output(raw_stream, expect_event, expect_keyword, monkeypatch):
    events = []

    class _FakeResponse:
        def raise_for_status(self):
            return None

        async def aiter_text(self):
            for piece in raw_stream.split("\n\n"):
                if piece:
                    yield piece + "\n\n"

    class _FakeStream:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, *args):
            return None

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return _FakeStream()

    monkeypatch.setattr("app.services.ai_parser.base_parser.httpx.AsyncClient", _FakeClient)

    async def run():
        parser = _StubParser()
        return [e async for e in parser.parse_stream(object(), "test", 1)]

    import app.services.ai_parser.base_parser as bp

    monkeypatch.setattr(bp.ai_config_crud, "get_config", lambda db, team_id: type("Cfg", (), {"model_name": "stub-model", "api_host": "http://stub"})())
    monkeypatch.setattr(bp.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: "key")


    events = asyncio.run(run())
    assert events, "parse_stream 应产出至少一个事件"
    matched = [e for e in events if e["event"] == expect_event]
    assert matched, f"应产出 {expect_event} 事件，实际: {events}"
    if expect_keyword is not None:
        assert expect_keyword in (matched[0].get("message") or ""), matched[0]
