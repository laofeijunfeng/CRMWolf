from types import SimpleNamespace

import pytest

import app.services.im_agent_gateway as gateway_module
from app.services.agent.input import AgentInputKind
from app.services.im_agent_gateway import IMAgentGateway
from app.services.im_feishu import FeishuBotService


@pytest.mark.asyncio
async def test_im_gateway_forwards_text_without_semantic_normalization(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "ok", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        None,
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=3,
        user_text="@CRMWolf 就按这个来",
        agent_content="就按这个来",
    )

    assert result["final_content"] == "ok"
    assert captured["content"] == "就按这个来"
    assert captured["turn_input"].kind == AgentInputKind.TEXT
    assert captured["turn_input"].metadata["raw_text"] == "@CRMWolf 就按这个来"


@pytest.mark.asyncio
async def test_im_gateway_maps_reaction_to_structured_confirmation(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(
        gateway_module.im_inbound_event_crud,
        "get_by_response_message_id",
        lambda *args, **kwargs: SimpleNamespace(raw_event={"message": {"chat_id": "chat_1", "thread_id": ""}}),
    )
    monkeypatch.setattr(
        gateway_module.agent_channel_session_crud,
        "get_by_scope",
        lambda *args, **kwargs: SimpleNamespace(agent_session_id=9),
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "done", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_reaction(
        None,
        team_id=1,
        user_id=2,
        provider="feishu",
        response_message_id="om_1",
        emoji_type="Get",
    )

    assert result["final_content"] == "done"
    assert captured["session_id"] == 9
    assert captured["turn_input"].kind == AgentInputKind.CONFIRM
    assert captured["turn_input"].metadata["emoji_type"] == "Get"


@pytest.mark.asyncio
async def test_im_gateway_ignores_unknown_reaction():
    gateway = IMAgentGateway()

    result = await gateway.handle_reaction(
        None,
        team_id=1,
        user_id=2,
        provider="feishu",
        response_message_id="om_1",
        emoji_type="Smile",
    )

    assert result is None


def test_feishu_text_extraction_removes_bot_mention_name():
    service = FeishuBotService()

    content = service._extract_content_text(
        '{"text":"@CRMWolf 确认"}',
        "text",
        [{"name": "CRMWolf", "mentioned_type": "bot"}],
    )

    assert content == "确认"
