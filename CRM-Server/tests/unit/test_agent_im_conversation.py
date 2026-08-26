"""IM channel projection over the single Agent UI application protocol."""

from uuid import UUID

import pytest

import app.services.agent.im_conversation as conversation_module
from app.schemas.agent import AgentSSEEventEnvelope
from app.services.agent.im_conversation import AgentIMConversationService
from app.services.agent.input import AgentChannelContext
from app.services.agent.ui.schemas import AgentUIEnvelope, TextAgentInput


@pytest.mark.asyncio
async def test_im_conversation_calls_typed_application_and_projects_agent_ui_final(monkeypatch) -> None:
    captured = {}
    final_message = {
        "schema_version": "crm.agent.ui.v1",
        "message_id": 12,
        "turn_id": "turn_12",
        "role": "assistant",
        "state": "final",
        "blocks": [
            {
                "id": "b_text_1",
                "type": "text",
                "format": "plain",
                "text": "请选择客户。",
            },
            {
                "id": "b_interaction_1",
                "type": "interaction",
                "interaction_id": "int_1",
                "interaction_type": "choice",
                "state": "ACTIVE",
                "prompt": "请选择客户。",
                "fields": [],
                "options": [
                    {
                        "value": "上海星云科技",
                        "label": "上海星云科技",
                        "description": None,
                        "disabled": False,
                    },
                    {
                        "value": "上海远景软件",
                        "label": "上海远景软件",
                        "description": None,
                        "disabled": False,
                    },
                ],
                "selection_mode": "single",
                "min_selections": 1,
                "max_selections": 1,
                "allow_blank": None,
                "submit_action_id": "act_1",
            },
        ],
        "suggested_actions": [],
        "metadata": {
            "route": "WORKFLOW",
            "result_set_id": None,
            "accessibility_label": "请选择客户。",
        },
    }

    async def fake_stream_chat_events(**kwargs):
        captured.update(kwargs)
        yield AgentSSEEventEnvelope.model_validate(
            {"event": "session", "session_id": 9, "session_key": "session_9"}
        )
        yield AgentSSEEventEnvelope.model_validate({
            "event": "agent_ui",
            "phase": "final",
            "message_id": 12,
            "turn_id": "turn_12",
            "sequence": 1,
            "message": final_message,
        })
        yield AgentSSEEventEnvelope.model_validate({"event": "done", "session_id": 9})

    monkeypatch.setattr(
        conversation_module.agent_application_service,
        "stream_chat_events",
        fake_stream_chat_events,
    )
    monkeypatch.setattr(conversation_module, "create_access_token", lambda *args, **kwargs: "token")

    result = await AgentIMConversationService().handle_message(
        request_input=TextAgentInput(type="text", text="列出客户"),
        client_request_id=UUID("03387da9-893a-53f9-8ed0-962e37c2ebae"),
        channel_context=AgentChannelContext(source="im", provider="feishu"),
        team_id=1,
        user_id=2,
        session_id=9,
    )

    assert captured["request_input"] == TextAgentInput(type="text", text="列出客户")
    assert captured["client_request_id"] == UUID("03387da9-893a-53f9-8ed0-962e37c2ebae")
    assert captured["channel_context"] == AgentChannelContext(source="im", provider="feishu")
    assert "content" not in captured
    assert "turn_input" not in captured
    assert result["final_content"] == "请选择客户。"
    assert result["message"] == AgentUIEnvelope.model_validate(final_message).model_dump(mode="json")
    assert result["interaction"]["submit_action_id"] == "act_1"
    assert [event["event"] for event in result["events"]] == ["session", "agent_ui", "done"]
