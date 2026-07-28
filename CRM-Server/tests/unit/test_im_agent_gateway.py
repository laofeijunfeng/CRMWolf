from types import SimpleNamespace

import pytest

import app.services.im_agent_gateway as gateway_module
import app.services.im_feishu as feishu_module
from app.services.agent.input import AgentInputKind
from app.models.agent import AgentTaskStatus
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
async def test_im_gateway_text_confirmation_uses_referenced_response_session(monkeypatch):
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
    monkeypatch.setattr(
        gateway_module.agent_task_crud,
        "get_latest_waiting",
        lambda *args, **kwargs: SimpleNamespace(
            id=1,
            status=AgentTaskStatus.WAITING_USER,
            state_json={"action": "create_customer_follow_up"},
            created_time=None,
        )
        if kwargs.get("session_id") == 9
        else None,
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "created", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        None,
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=10,
        user_text="是",
        agent_content="引用消息：\n请确认是否创建这条跟进记录？\n\n本次指令：\n是",
        chat_id="chat_1",
        thread_id="om_thread",
        referenced_message_ids=["om_bot_reply"],
    )

    assert result["final_content"] == "created"
    assert captured["session_id"] == 9
    assert captured["content"] == "确认"
    assert captured["turn_input"].kind == AgentInputKind.CONFIRM


@pytest.mark.asyncio
async def test_im_gateway_text_confirmation_falls_back_to_recent_chat_task(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(
        gateway_module.agent_task_crud,
        "get_latest_waiting",
        lambda *args, **kwargs: SimpleNamespace(
            id=1,
            status=AgentTaskStatus.WAITING_USER,
            state_json={"action": "create_customer_follow_up"},
            created_time=None,
        )
        if kwargs.get("session_id") == 9
        else None,
    )
    monkeypatch.setattr(
        gateway_module.agent_channel_session_crud,
        "list_by_chat",
        lambda *args, **kwargs: [SimpleNamespace(agent_session_id=9)],
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "created", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        None,
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=10,
        user_text="是",
        agent_content="是",
        chat_id="chat_1",
        thread_id="om_thread",
        referenced_message_ids=[],
    )

    assert result["final_content"] == "created"
    assert captured["session_id"] == 9
    assert captured["turn_input"].kind == AgentInputKind.CONFIRM


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


def test_feishu_referenced_message_ids_prefers_parent_before_root():
    service = FeishuBotService()

    ids = service._referenced_message_ids({"root_id": "om_root", "parent_id": "om_parent"})

    assert ids == ["om_parent", "om_root"]


@pytest.mark.asyncio
async def test_feishu_reaction_event_uses_official_top_level_user_id(monkeypatch):
    service = FeishuBotService()
    captured = {}

    monkeypatch.setattr(
        feishu_module.user_oauth_account_crud,
        "get_by_open_id",
        lambda db, team_id, provider, open_id: SimpleNamespace(user_id=7),
    )

    class FakeIMAgentGateway:
        def intent_from_emoji(self, emoji_type):
            return "confirm" if emoji_type == "Yes" else None

        async def handle_reaction(self, db, **kwargs):
            captured.update(kwargs)
            return {"final_content": "已确认", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(feishu_module, "im_agent_gateway", FakeIMAgentGateway())

    reply_to_message_id, reply_text = await service._handle_reaction_event(
        None,
        SimpleNamespace(team_id=1),
        {
            "message_id": "om_reply",
            "operator_type": "user",
            "user_id": {"open_id": "ou_user"},
            "reaction_type": {"emoji_type": "Yes"},
        },
        "im.message.reaction.created_v1",
    )

    assert reply_to_message_id == "om_reply"
    assert reply_text == "已确认"
    assert captured["user_id"] == 7
    assert captured["response_message_id"] == "om_reply"
    assert captured["emoji_type"] == "Yes"


@pytest.mark.asyncio
async def test_feishu_reaction_deleted_event_is_ignored(monkeypatch):
    service = FeishuBotService()

    class FakeIMAgentGateway:
        def intent_from_emoji(self, emoji_type):
            raise AssertionError("deleted reaction must not be mapped")

    monkeypatch.setattr(feishu_module, "im_agent_gateway", FakeIMAgentGateway())

    reply_to_message_id, reply_text = await service._handle_reaction_event(
        None,
        SimpleNamespace(team_id=1),
        {
            "message_id": "om_reply",
            "operator_type": "user",
            "user_id": {"open_id": "ou_user"},
            "reaction_type": {"emoji_type": "Yes"},
        },
        "im.message.reaction.deleted_v1",
    )

    assert reply_to_message_id is None
    assert reply_text is None
