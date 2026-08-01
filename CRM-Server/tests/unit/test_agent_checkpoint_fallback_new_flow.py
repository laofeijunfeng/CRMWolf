from types import SimpleNamespace

import pytest

from app.services.agent.checkpoint_fallback_runtime import CheckpointFallbackNewFlowAdapter


class FakeGraphService:
    async def stream_events(self, input_state):
        yield {
            "event": "business_context_loaded",
            "customer": {"id": 101, "account_name": "越秀金融"},
        }
        yield {
            "event": "confirmation_required",
            "action": "create_customer_activity",
            "payload": {"customer_id": 101, "content": "已沟通项目进展"},
            "content": "请确认是否创建这条跟进记录？",
        }
        yield {"event": "final", "content": f"已处理：{input_state['content']}"}


@pytest.mark.asyncio
async def test_checkpoint_fallback_new_flow_adapter_applies_event_side_effects(monkeypatch):
    adapter = CheckpointFallbackNewFlowAdapter()
    db = object()
    session = SimpleNamespace(id=3, context_json={"current_customer": {"id": 9}})
    remembered_customers = []
    waiting_events = []

    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.session_state._remember_current_customer",
        lambda db_arg, session_arg, customer: remembered_customers.append(customer),
    )
    monkeypatch.setattr(
        "app.services.agent.new_flow_effects.task_factory._create_waiting_task_from_event",
        lambda db_arg, event, team_id, user_id, session_arg: waiting_events.append(event),
    )

    assistant_ref = {"content": None}
    events = [
        event
        async for event in adapter.stream_events(
            db,
            session=session,
            team_id=1,
            user_id=2,
            content="今天和越秀金融沟通",
            authorization="Bearer test",
            switch_notice="我先切到新流程处理。",
            assistant_ref=assistant_ref,
            graph_service=FakeGraphService(),
        )
    ]

    assert remembered_customers == [{"id": 101, "account_name": "越秀金融"}]
    assert waiting_events[0]["event"] == "confirmation_required"
    assert events[-1] == {
        "event": "final",
        "content": "我先切到新流程处理。\n\n已处理：今天和越秀金融沟通",
    }
    assert assistant_ref["content"] == "我先切到新流程处理。\n\n已处理：今天和越秀金融沟通"
