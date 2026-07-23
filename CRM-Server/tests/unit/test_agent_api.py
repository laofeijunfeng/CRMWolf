"""CRM AI Agent API tests."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.api import agent as agent_api
from app.core.database import Base
from app.models.agent import AgentIdempotencyKey, AgentMessage, AgentSession, AgentTask, AgentToolCall


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def _build_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        AgentSession.__table__,
        AgentMessage.__table__,
        AgentTask.__table__,
        AgentToolCall.__table__,
        AgentIdempotencyKey.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(agent_api.router)
    app.dependency_overrides[agent_api.get_db] = lambda: Session()
    app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
    app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="销售李",
        status="active",
    )
    monkeypatch.setattr(agent_api, "SessionLocal", lambda: Session())

    return TestClient(app), engine


def test_agent_session_and_stream_api(monkeypatch):
    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        assert create_response.status_code == 201, create_response.text
        session = create_response.json()
        assert session["team_id"] == 1
        assert session["user_id"] == 2
        assert session["title"] == "跟进会话"

        list_response = client.get("/v1/agent/sessions")
        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["total"] == 1

        stream_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "今天和越秀金融沟通了项目进展"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert stream_response.status_code == 200, stream_response.text
        stream_text = stream_response.text
        assert '"event": "message"' in stream_text
        assert "今天和越秀金融沟通了项目进展" in stream_text

        messages_response = client.get(f"/v1/agent/sessions/{session['id']}/messages")
        assert messages_response.status_code == 200, messages_response.text
        messages_body = messages_response.json()
        assert messages_body["total"] == 2
        assert [item["role"] for item in messages_body["items"]] == ["USER", "ASSISTANT"]
    finally:
        engine.dispose()
