"""Agent memory snapshot tests."""
from types import SimpleNamespace

from app.services.agent import memory as agent_memory_module
from app.services.agent.memory import AgentMemoryService


class FakeAgentMessageCRUD:
    def __init__(self, messages):
        self.messages = messages
        self.calls = []

    def list_by_session(self, db, *, session_id, team_id=None, user_id=None, skip=0, limit=100):
        self.calls.append({
            "session_id": session_id,
            "team_id": team_id,
            "user_id": user_id,
            "skip": skip,
            "limit": limit,
        })
        return self.messages[skip:skip + limit], len(self.messages)


class FakeAgentTaskCRUD:
    def get_latest_waiting(self, db, *, session_id, team_id, user_id):
        return None


def test_agent_memory_loads_latest_messages_and_recent_follow_up_task_refs(monkeypatch):
    messages = [
        SimpleNamespace(
            role="USER",
            event_type="user_message",
            content=f"message {index}",
            payload_json=None,
            created_time=None,
        )
        for index in range(15)
    ]
    messages[-1].payload_json = {
        "trace_events": [{
            "event": "agent_read_tool_executed",
            "recent_follow_up_tasks": [{
                "id": "fut_00000000000000000000000000001001",
                "title": "确认预算进展",
                "customer_name": "越秀金融",
                "status": "open",
                "due_at": "2026-08-06T09:30:00",
            }],
        }],
    }
    message_crud = FakeAgentMessageCRUD(messages)
    monkeypatch.setattr(agent_memory_module, "agent_message_crud", message_crud)
    monkeypatch.setattr(agent_memory_module, "agent_task_crud", FakeAgentTaskCRUD())

    snapshot = AgentMemoryService().load_snapshot(
        object(),
        team_id=1,
        user_id=2,
        session_id=3,
        message_limit=12,
    )

    assert message_crud.calls[-1]["skip"] == 3
    assert snapshot.recent_messages[0]["content"] == "message 3"
    assert snapshot.recent_messages[-1]["content"] == "message 14"
    assert snapshot.recent_follow_up_tasks[0]["id"] == "fut_00000000000000000000000000001001"
