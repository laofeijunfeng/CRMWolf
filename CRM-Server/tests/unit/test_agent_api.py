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
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentTask,
    AgentTaskStatus,
    AgentToolCall,
)
from app.services.agent.tools.base import AgentToolResult


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


def test_agent_stream_creates_waiting_task_and_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "confirmation_required",
                "action": "create_customer_follow_up",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "content": input_state["content"],
                    "next_action": "下周三继续跟进",
                    "next_follow_time_text": "下周三",
                },
            }
            yield {"event": "final", "content": "请确认是否创建这条跟进记录？"}

    class FakeToolService:
        async def create_customer_follow_up(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["customer_name"] == "越秀金融"
            assert kwargs["content"] == "今天和越秀金融的王总沟通了项目进展，下周三继续跟进"
            assert kwargs["next_follow_time"] == "下周三"
            return AgentToolResult(
                tool_name="create_customer_follow_up",
                success=True,
                data={"id": 9001, "customer_id": 101},
                tool_call_id=7001,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "confirmation_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "跟进记录已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {"id": 9001, "customer_id": 101}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_resolves_customer_selection_before_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "customer_selection_required",
                "action": "select_customer_for_follow_up",
                "customers": [
                    {"id": 101, "account_name": "越秀金融"},
                    {"id": 102, "account_name": "越秀金融科技"},
                ],
                "payload": {
                    "content": input_state["content"],
                    "next_action": "下周三继续跟进",
                    "next_follow_time_text": "下周三",
                },
            }
            yield {"event": "final", "content": "我找到了多个可能的客户，请回复序号或客户名称确认。"}

    class FakeToolService:
        async def create_customer_follow_up(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 102
            assert kwargs["customer_name"] == "越秀金融科技"
            assert kwargs["content"] == "今天和越秀金融的王总沟通了项目进展，下周三继续跟进"
            assert kwargs["next_follow_time"] == "下周三"
            return AgentToolResult(
                tool_name="create_customer_follow_up",
                success=True,
                data={"id": 9002, "customer_id": 102},
                tool_call_id=7002,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "跟进会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "今天和越秀金融的王总沟通了项目进展，下周三继续跟进",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "customer_selection_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        select_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "2"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert select_response.status_code == 200, select_response.text
        assert '"event": "customer_selected"' in select_response.text
        assert "请确认是否创建这条跟进记录" in select_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "跟进记录已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.target_id == 102
            assert task.result_json == {"id": 9002, "customer_id": 102}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_contact_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "contact_fields_required",
                "action": "collect_contact_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "contact": {"name": "王总", "is_decision_maker": False},
                    "missing_fields": ["mobile", "position", "gender"],
                },
            }
            yield {"event": "final", "content": "还需要补充：手机号、职务、性别。"}

    class FakeToolService:
        async def create_contact(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["contact"] == {
                "name": "王总",
                "is_decision_maker": False,
                "mobile": "13800138000",
                "position": "总经理",
                "gender": "1",
            }
            return AgentToolResult(
                tool_name="create_contact",
                success=True,
                data={"id": 8001, "customer_id": 101, "name": "王总"},
                tool_call_id=7101,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "联系人会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建联系人王总"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "contact_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "手机号13800138000，职务总经理，男"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "contact_fields_completed"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "联系人已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {"id": 8001, "customer_id": 101, "name": "王总"}
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_invoice_title_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "invoice_title_fields_required",
                "action": "collect_invoice_title_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "invoice_title": {"title_type": "COMPANY"},
                    "missing_fields": ["title", "taxpayer_id"],
                    "set_default": False,
                },
            }
            yield {"event": "final", "content": "还需要补充：开票抬头、纳税人识别号。"}

    class FakeToolService:
        async def create_invoice_title(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["customer_id"] == 101
            assert kwargs["invoice_title"] == {
                "title_type": "COMPANY",
                "title": "越秀金融控股有限公司",
                "taxpayer_id": "91440000123456789X",
            }
            assert kwargs["set_default"] is True
            return AgentToolResult(
                tool_name="create_invoice_title",
                success=True,
                data={
                    "invoice_title": {
                        "id": 6001,
                        "customer_id": 101,
                        "title": "越秀金融控股有限公司",
                    },
                    "set_default": True,
                },
                tool_call_id=7201,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "发票抬头会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建发票抬头"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "invoice_title_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "抬头是越秀金融控股有限公司，税号91440000123456789X，设为默认",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "invoice_title_fields_completed"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "发票抬头已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {
                "invoice_title": {
                    "id": 6001,
                    "customer_id": 101,
                    "title": "越秀金融控股有限公司",
                },
                "set_default": True,
            }
        finally:
            db.close()
    finally:
        engine.dispose()


def test_agent_stream_collects_deployment_info_fields_then_executes_confirmation(monkeypatch):
    class FakeGraphService:
        async def stream_events(self, input_state):
            yield {
                "event": "deployment_info_fields_required",
                "action": "collect_deployment_info_fields",
                "customer": {"id": 101, "account_name": "越秀金融"},
                "payload": {
                    "customer_id": 101,
                    "deployment_info": {"customer_id": 101, "is_default": False},
                    "missing_fields": ["deployment_name", "server_address", "authorized_users"],
                },
            }
            yield {"event": "final", "content": "还需要补充：部署名称、服务器地址、授权人数。"}

    class FakeToolService:
        async def create_deployment_info(self, context, **kwargs):
            assert context.authorization == "Bearer test-token"
            assert context.task_id is not None
            assert kwargs["deployment_info"] == {
                "customer_id": 101,
                "is_default": True,
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
                "authorized_users": 100,
            }
            return AgentToolResult(
                tool_name="create_deployment_info",
                success=True,
                data={
                    "id": 6101,
                    "customer_id": 101,
                    "deployment_name": "生产环境",
                },
                tool_call_id=7301,
            )

    monkeypatch.setattr(agent_api, "crm_agent_graph_service", FakeGraphService())
    monkeypatch.setattr(agent_api, "CRMAgentToolService", lambda: FakeToolService())

    client, engine = _build_client(monkeypatch)
    try:
        create_response = client.post("/v1/agent/sessions", json={"title": "部署信息会话"})
        session = create_response.json()

        plan_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "帮我给越秀金融创建部署信息"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert plan_response.status_code == 200, plan_response.text
        assert '"event": "deployment_info_fields_required"' in plan_response.text
        assert '"task_id": 1' in plan_response.text

        fill_response = client.post(
            "/v1/agent/chat/stream",
            json={
                "session_id": session["id"],
                "content": "部署名称是生产环境，服务器地址 https://crm.example.com，授权人数100，设为默认",
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert fill_response.status_code == 200, fill_response.text
        assert '"event": "deployment_info_fields_completed"' in fill_response.text
        assert "请确认是否为" in fill_response.text

        confirm_response = client.post(
            "/v1/agent/chat/stream",
            json={"session_id": session["id"], "content": "是"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert '"event": "task_completed"' in confirm_response.text
        assert "部署信息已创建" in confirm_response.text

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            task = db.query(AgentTask).one()
            assert task.status == AgentTaskStatus.COMPLETED
            assert task.result_json == {
                "id": 6101,
                "customer_id": 101,
                "deployment_name": "生产环境",
            }
        finally:
            db.close()
    finally:
        engine.dispose()
