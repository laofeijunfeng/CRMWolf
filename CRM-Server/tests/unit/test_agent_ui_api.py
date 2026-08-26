"""API behavior tests for the authoritative Agent UI protocol."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import agent as agent_api
from app.schemas.agent import AgentSSEDoneEvent, AgentSSEEventEnvelope

_CLIENT_REQUEST_ID = "6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be"


def _build_stream_client(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="销售李",
        status="active",
    )

    async def fake_stream_chat_events(**kwargs):
        yield AgentSSEEventEnvelope(
            root=AgentSSEDoneEvent(
                event="done",
                session_id=kwargs.get("session_id") or 1,
            )
        )

    monkeypatch.setattr(
        agent_api.agent_application_service,
        "stream_chat_events",
        fake_stream_chat_events,
    )
    return TestClient(app)


def test_chat_stream_rejects_legacy_content_request(monkeypatch) -> None:
    client = _build_stream_client(monkeypatch)

    response = client.post(
        "/v1/agent/chat/stream",
        headers={"Authorization": "Bearer test-token"},
        json={"content": "旧协议请求"},
    )

    assert response.status_code == 422


def test_chat_stream_accepts_typed_input_and_forwards_request_identity(monkeypatch) -> None:
    captured = {}
    app = FastAPI()
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="销售李",
        status="active",
    )

    async def fake_stream_chat_events(**kwargs):
        captured.update(kwargs)
        yield AgentSSEEventEnvelope(
            root=AgentSSEDoneEvent(event="done", session_id=9)
        )

    monkeypatch.setattr(
        agent_api.agent_application_service,
        "stream_chat_events",
        fake_stream_chat_events,
    )
    client = TestClient(app)

    response = client.post(
        "/v1/agent/chat/stream",
        headers={"Authorization": "Bearer test-token"},
        json={
            "session_id": 9,
            "client_request_id": _CLIENT_REQUEST_ID,
            "input": {"type": "text", "text": "我在上海有哪些客户"},
        },
    )

    assert response.status_code == 200
    assert captured["session_id"] == 9
    assert str(captured["client_request_id"]) == _CLIENT_REQUEST_ID
    assert captured["request_input"].type == "text"
    assert captured["request_input"].text == "我在上海有哪些客户"
    assert "content" not in captured
    assert "turn_input" not in captured


def test_agent_sse_event_union_rejects_unknown_events() -> None:
    with pytest.raises(ValidationError):
        AgentSSEEventEnvelope.model_validate(
            {"event": "legacy_message", "session_id": 9}
        )


def test_agent_sse_event_union_rejects_unknown_delta_operations() -> None:
    with pytest.raises(ValidationError):
        AgentSSEEventEnvelope.model_validate(
            {
                "event": "agent_ui",
                "phase": "delta",
                "message_id": 9,
                "turn_id": "turn_9",
                "sequence": 1,
                "operations": [
                    {"op": "replace_table", "block_id": "b_table", "delta": "非法操作"}
                ],
            }
        )


def test_agent_sse_event_union_rejects_invalid_final_message() -> None:
    with pytest.raises(ValidationError):
        AgentSSEEventEnvelope.model_validate(
            {
                "event": "agent_ui",
                "phase": "final",
                "message_id": 9,
                "turn_id": "turn_9",
                "sequence": 1,
                "message": {
                    "schema_version": "crm.agent.ui.v1",
                    "message_id": 9,
                    "turn_id": "turn_9",
                    "role": "assistant",
                    "state": "final",
                    "blocks": [],
                    "suggested_actions": [],
                    "metadata": {},
                    "legacy_payload": {},
                },
            }
        )


def test_message_history_returns_only_validated_agent_ui_envelopes(monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.types import BigInteger

    from app.core.database import Base
    from app.models.agent import AgentMessage, AgentSession
    from app.schemas.agent_persistence import (
        AgentAssistantMessageCreate,
        AgentTurnStart,
        AgentUIMessageBody,
    )
    from app.services.agent.turns import AgentTurnRepository
    from app.services.agent.ui.schemas import AgentUIMetadata, TextBlock

    @compiles(BigInteger, "sqlite")
    def _bigint_to_sqlite_int(element, compiler, **kw):
        return "INTEGER"

    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        session = AgentSession(session_key="agent-session-history", team_id=1, user_id=2)
        db.add(session)
        db.commit()
        db.refresh(session)
        repository = AgentTurnRepository()
        user_body = AgentUIMessageBody(
            state="final",
            blocks=[TextBlock(id="b_user_text_1", type="text", format="plain", text="你好")],
            suggested_actions=[],
            metadata=AgentUIMetadata(accessibility_label="你好"),
        )
        started = repository.begin(
            db,
            AgentTurnStart(
                team_id=1,
                user_id=2,
                session_id=session.id,
                client_request_id=_CLIENT_REQUEST_ID,
                input_fingerprint="a" * 64,
                content="你好",
                ui=user_body,
            ),
        )
        assistant_body = AgentUIMessageBody(
            state="final",
            blocks=[TextBlock(id="b_text_1", type="text", format="plain", text="你好！")],
            suggested_actions=[],
            metadata=AgentUIMetadata(route="CHITCHAT", accessibility_label="你好！"),
        )
        repository.complete(
            db,
            AgentAssistantMessageCreate(
                team_id=1,
                user_id=2,
                session_id=session.id,
                turn_id=started.user_message.turn_id,
                content="你好！",
                ui=assistant_body,
                diagnostics={"runtime_events": []},
            ),
        )
        state_update_body = AgentUIMessageBody(
            state="final",
            blocks=[TextBlock(id="b_state_update", type="text", format="plain", text="内部状态")],
            suggested_actions=[],
            metadata=AgentUIMetadata(display="STATE_UPDATE"),
        )
        state_update_turn = repository.begin(
            db,
            AgentTurnStart(
                team_id=1,
                user_id=2,
                session_id=session.id,
                client_request_id="70a2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
                input_fingerprint="b" * 64,
                content="内部状态",
                ui=state_update_body,
            ),
        )
        repository.complete(
            db,
            AgentAssistantMessageCreate(
                team_id=1,
                user_id=2,
                session_id=session.id,
                turn_id=state_update_turn.user_message.turn_id,
                content="内部状态",
                ui=state_update_body,
                diagnostics={"runtime_events": []},
            ),
        )
        db.commit()
        session_id = session.id

    app = FastAPI()
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api.get_db] = lambda: session_factory()
    app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="销售李",
        status="active",
    )
    projection_calls = []

    class _FakeProjection:
        async def project_pending(self, db, **kwargs):
            projection_calls.append((db, kwargs))
            return 0

    monkeypatch.setattr(
        agent_api,
        "follow_up_confirmation_agent_ui_projection",
        _FakeProjection(),
        raising=False,
    )
    monkeypatch.setattr(
        agent_api,
        "permission_crud",
        SimpleNamespace(
            get_user_permissions=lambda db, user_id, team_id: [
                SimpleNamespace(code="follow_up_task:edit:own")
            ]
        ),
        raising=False,
    )
    client = TestClient(app)
    try:
        response = client.get(
            f"/v1/agent/sessions/{session_id}/messages",
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        engine.dispose()

    assert response.status_code == 200
    assert len(projection_calls) == 1
    _, projection_kwargs = projection_calls[0]
    assert projection_kwargs == {
        "team_id": 1,
        "user_id": 2,
        "session_id": session_id,
        "authorization": "Bearer test-token",
        "permission_codes": frozenset({"follow_up_task:edit:own"}),
    }
    payload = response.json()
    assert payload["total"] == 2
    assert [item["role"] for item in payload["items"]] == ["user", "assistant"]
    assert all(item["schema_version"] == "crm.agent.ui.v1" for item in payload["items"])
    serialized = str(payload)
    assert "payload_json" not in serialized
    assert "event_type" not in serialized
    assert "linked_follow_up_task_confirmations" not in serialized
