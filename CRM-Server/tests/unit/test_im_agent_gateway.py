from types import SimpleNamespace

import pytest

import app.services.im_agent_gateway as gateway_module
import app.services.im_feishu as feishu_module
from app.models.agent import AgentTaskStatus
from app.services.agent.input import AgentInputKind
from app.services.follow_up_task_confirmation_channel_service import (
    FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
    FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
)
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
        lambda *args, **kwargs: SimpleNamespace(agent_session_id=9, agent_task_id=1),
    )
    monkeypatch.setattr(
        gateway_module.agent_task_crud,
        "get_by_id",
        lambda *args, **kwargs: SimpleNamespace(
            id=1,
            session_id=9,
            status=AgentTaskStatus.WAITING_USER,
        ),
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "created", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        object(),
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
async def test_im_gateway_field_supplement_uses_referenced_pending_session(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(
        gateway_module.im_inbound_event_crud,
        "get_by_response_message_id",
        lambda *args, **kwargs: SimpleNamespace(agent_session_id=9, agent_task_id=1),
    )
    monkeypatch.setattr(
        gateway_module.agent_task_crud,
        "get_by_id",
        lambda *args, **kwargs: SimpleNamespace(
            id=1,
            session_id=9,
            status=AgentTaskStatus.WAITING_USER,
        ),
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "field collected", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        object(),
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=10,
        user_text="采购人数 10 万，买断，新购，公开招投标",
        agent_content="引用消息：\n还需要补充：采购用户数、授权模式、采购类型、采购方式。\n\n本次指令：\n采购人数 10 万，买断，新购，公开招投标",
        chat_id="chat_1",
        thread_id="om_thread",
        referenced_message_ids=["om_bot_reply"],
    )

    assert result["final_content"] == "field collected"
    assert captured["session_id"] == 9
    assert captured["content"] == "采购人数 10 万，买断，新购，公开招投标"
    assert captured["turn_input"].kind == AgentInputKind.TEXT
    assert captured["turn_input"].metadata["reply_to_message_ids"] == ["om_bot_reply"]
    assert "还需要补充" not in captured["turn_input"].content


@pytest.mark.asyncio
async def test_im_gateway_referenced_choice_text_uses_exact_pending_session_without_history_scan(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(gateway, "_resolve_referenced_pending_session_id", lambda *args, **kwargs: 91)

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "resumed", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        None,
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=10,
        user_text="1",
        agent_content="引用消息：\n你想继续哪个草稿？\n\n本次指令：\n1",
        referenced_message_ids=["om_bot_reply"],
    )

    assert result["final_content"] == "resumed"
    assert captured["session_id"] == 91
    assert captured["content"] == "1"
    assert captured["turn_input"].kind == AgentInputKind.TEXT
    assert captured["turn_input"].metadata["reply_to_message_ids"] == ["om_bot_reply"]
    assert "selected_task_id" not in captured["turn_input"].metadata


@pytest.mark.asyncio
async def test_im_gateway_does_not_bind_unreferenced_business_text_to_old_confirmation(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "new flow", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        None,
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=10,
        user_text="今天联系了,还没有进展,下周五再说",
        agent_content="今天联系了,还没有进展,下周五再说",
    )

    assert result["final_content"] == "new flow"
    assert captured["session_id"] == 10
    assert captured["turn_input"].content == "今天联系了,还没有进展,下周五再说"
    assert "business_action" not in captured["turn_input"].metadata
    assert "case_public_id" not in captured["turn_input"].metadata


@pytest.mark.asyncio
async def test_im_gateway_binds_referenced_follow_up_confirmation_session(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(
        gateway,
        "_resolve_referenced_confirmation_target",
        lambda *args, **kwargs: gateway_module.IMConfirmationReplyTarget(
            session_id=91,
            delivery_public_id="fud_11111111111111111111111111111111",
            case_public_id="fuc_22222222222222222222222222222222",
            interaction_id="int_follow_up_confirmation",
            prompt_delivery_key="projection:test",
        ),
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "referenced", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        object(),
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=10,
        user_text="下周五再说",
        agent_content="引用消息:\n你有一项上次跟进需要确认\n\n本次指令:\n下周五再说",
        referenced_message_ids=["om_bot_reply"],
    )

    assert result["final_content"] == "referenced"
    assert captured["session_id"] == 91
    assert captured["turn_input"].content == "下周五再说"
    assert captured["turn_input"].metadata["reply_to_message_ids"] == ["om_bot_reply"]
    assert captured["turn_input"].metadata["case_public_id"] == "fuc_22222222222222222222222222222222"


@pytest.mark.asyncio
async def test_im_gateway_uses_hidden_reply_binding_before_channel_fallback(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(
        gateway_module.im_inbound_event_crud,
        "get_by_response_message_id",
        lambda *args, **kwargs: SimpleNamespace(
            agent_session_id=91,
            agent_task_id=101,
            raw_event={"message": {}},
        ),
    )
    monkeypatch.setattr(
        gateway_module.agent_task_crud,
        "get_by_id",
        lambda *args, **kwargs: SimpleNamespace(id=101, session_id=91, status=AgentTaskStatus.WAITING_USER),
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "field collected", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_text(
        object(),
        team_id=1,
        user_id=2,
        provider="feishu",
        session_id=10,
        user_text="交付总监",
        agent_content="引用消息：\n联系人是什么角色？\n\n本次指令：\n交付总监",
        referenced_message_ids=["om_bot_reply"],
    )

    assert result["final_content"] == "field collected"
    assert captured["session_id"] == 91
    assert captured["content"] == "交付总监"


@pytest.mark.asyncio
async def test_im_gateway_text_confirmation_without_exact_binding_stays_plain_text(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(
        gateway_module.im_inbound_event_crud,
        "get_by_response_message_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no referenced message should be queried")),
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "new flow", "interaction": None, "events": [], "im_events": []}

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

    assert result["final_content"] == "new flow"
    assert captured["session_id"] == 10
    assert captured["content"] == "是"
    assert captured["turn_input"].kind == AgentInputKind.TEXT


@pytest.mark.asyncio
async def test_im_gateway_does_not_scan_chat_sessions_for_confirmation(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "plain", "interaction": None, "events": [], "im_events": []}

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

    assert result["final_content"] == "plain"
    assert captured["session_id"] == 10
    assert captured["turn_input"].kind == AgentInputKind.TEXT


@pytest.mark.asyncio
async def test_im_gateway_maps_reaction_to_structured_confirmation(monkeypatch):
    gateway = IMAgentGateway()
    captured = {}

    monkeypatch.setattr(
        gateway_module.im_inbound_event_crud,
        "get_by_response_message_id",
        lambda *args, **kwargs: SimpleNamespace(agent_session_id=9, agent_task_id=1),
    )
    monkeypatch.setattr(
        gateway_module.agent_task_crud,
        "get_by_id",
        lambda *args, **kwargs: SimpleNamespace(
            id=1,
            session_id=9,
            status=AgentTaskStatus.WAITING_USER,
        ),
    )

    async def fake_handle_message(**kwargs):
        captured.update(kwargs)
        return {"final_content": "done", "interaction": None, "events": [], "im_events": []}

    monkeypatch.setattr(gateway_module.agent_im_conversation_service, "handle_message", fake_handle_message)

    result = await gateway.handle_reaction(
        object(),
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

    delivery = await service._handle_reaction_event(
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

    assert delivery.reply_to_message_id == "om_reply"
    assert delivery.text == "已确认"
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

    delivery = await service._handle_reaction_event(
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

    assert delivery.reply_to_message_id is None
    assert delivery.text is None


def test_feishu_extracts_hidden_reply_binding_from_waiting_agent_event():
    service = FeishuBotService()

    binding = service._extract_reply_binding({
        "session": {"event": "session", "session_id": "88"},
        "final_content": "还需要补充联系人角色。",
        "events": [
            {"event": "session", "session_id": 88},
            {"event": "message", "content": "x"},
            {"event": "contact_fields_required", "task_id": "177"},
            {"event": "final", "content": "还需要补充联系人角色。"},
        ],
    })

    assert binding.agent_session_id == 88
    assert binding.agent_task_id == 177
    assert binding.agent_interaction_type == "contact_fields_required"


def test_feishu_renders_non_confirmation_choice_options():
    service = FeishuBotService()

    text = service._render_im_reply({
        "final_content": "你想继续哪个草稿？",
        "interaction": {
            "type": "choice",
            "business_action": "select_suspended_task",
            "choices": [
                {"label": "继续处理：广州睿狐增购10个账号补商机信息", "value": "继续处理：广州睿狐增购10个账号补商机信息"},
                {"label": "继续处理：广州睿狐创建商机确认", "value": "继续处理：广州睿狐创建商机确认"},
            ],
        },
    })

    assert "1. 继续处理：广州睿狐增购10个账号补商机信息" in text
    assert "2. 继续处理：广州睿狐创建商机确认" in text
    assert "回复序号或选项文字" in text
    assert "回复「是」确认" not in text


def test_feishu_renders_follow_up_confirmation_choices_and_keeps_session_binding():
    service = FeishuBotService()
    result = {
        "session": {"event": "session", "session_id": 88},
        "final_content": "上次你说要确认预算，这个有进展吗？",
        "interaction": {
            "type": "choice",
            "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
            "choices": [
                {"label": "已完成", "value": "已完成"},
                {"label": "先放着", "value": "先放着"},
                {"label": "不管了", "value": "不管了"},
            ],
        },
        "events": [
            {"event": "session", "session_id": 88},
            {
                "event": FOLLOW_UP_CONFIRMATION_PROMPT_EVENT,
                "interaction": {
                    "business_action": FOLLOW_UP_CONFIRMATION_BUSINESS_ACTION,
                    "payload": {"case_public_id": "fuc_11111111111111111111111111111111"},
                },
            },
        ],
    }

    text = service._render_im_reply(result)
    binding = service._extract_reply_binding(result)

    assert "1. 已完成" in text
    assert "2. 先放着" in text
    assert "3. 不管了" in text
    assert "回复序号或选项文字" in text
    assert "回复「是」确认" not in text
    assert binding.agent_session_id == 88
    assert binding.agent_task_id is None
