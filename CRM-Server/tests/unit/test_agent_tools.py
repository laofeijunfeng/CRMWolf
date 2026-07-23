"""CRM AI Agent tool adapter tests."""
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger
import pytest

from app.core.database import Base
from app.models.agent import (
    AgentIdempotencyKey,
    AgentMessage,
    AgentSession,
    AgentTask,
    AgentToolCall,
    AgentToolCallStatus,
)
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.tools.service import CRMAgentToolService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


class FakeCRMAPIClient:
    def __init__(self) -> None:
        self.calls = []

    async def request(self, method, path, authorization, *, params=None, json=None):
        self.calls.append({
            "method": method,
            "path": path,
            "authorization": authorization,
            "params": params,
            "json": json,
        })
        if method == "GET" and path == "/v1/customers/":
            return {"items": [{"id": 101, "account_name": "越秀金融"}], "total": 1}
        if method == "POST" and path == "/v1/customers/ai/create":
            return {
                "id": 9001,
                "customer_id": json["customer_id"],
                "content": json["content"],
                "next_follow_time": "2026-07-29T00:00:00",
            }
        if method == "POST" and path == "/v1/invoice-titles":
            return {"id": 6001, "customer_id": params["customer_id"], **json, "is_default": False}
        if method == "PATCH" and path == "/v1/invoice-titles/6001/set-default":
            return {"id": 6001, "customer_id": 101, "title": "越秀金融控股有限公司", "is_default": True}
        if method == "POST" and path == "/v1/deployment-infos/":
            return {"id": 6101, **json}
        return {}


def _db_session():
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
    session = Session()
    return engine, session


def _context(db):
    return AgentToolContext(
        db=db,
        team_id=1,
        user_id=2,
        session_id=3,
        authorization="Bearer test-token",
    )


@pytest.mark.asyncio
async def test_agent_tool_search_customers_calls_existing_api_and_audits():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.search_customers(_context(db), "越秀金融", limit=5)

        assert result.success is True
        assert result.data["total"] == 1
        assert fake_client.calls == [{
            "method": "GET",
            "path": "/v1/customers/",
            "authorization": "Bearer test-token",
            "params": {"keyword": "越秀金融", "limit": 5, "scope": "accessible"},
            "json": None,
        }]

        tool_call = db.query(AgentToolCall).one()
        assert tool_call.tool_name == "search_customers"
        assert tool_call.status == AgentToolCallStatus.SUCCESS
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_follow_up_is_idempotent():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    context = _context(db)
    try:
        first = await service.create_customer_follow_up(
            context,
            customer_id=101,
            customer_name="越秀金融",
            content="今天和王总沟通了项目进展",
            next_action="下周三确认进展",
            next_follow_time="下周三",
            idempotency_suffix="msg-001",
        )
        second = await service.create_customer_follow_up(
            context,
            customer_id=101,
            customer_name="越秀金融",
            content="今天和王总沟通了项目进展",
            next_action="下周三确认进展",
            next_follow_time="下周三",
            idempotency_suffix="msg-001",
        )

        assert first.success is True
        assert second.success is True
        assert second.idempotent_replay is True
        assert len(fake_client.calls) == 1
        assert fake_client.calls[0]["path"] == "/v1/customers/ai/create"
        assert fake_client.calls[0]["json"]["customer_name"] == "越秀金融"
        assert fake_client.calls[0]["json"]["next_follow_time"] == "下周三"
        assert db.query(AgentIdempotencyKey).count() == 1
        assert db.query(AgentToolCall).count() == 1
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_invoice_title_calls_existing_api_and_sets_default():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.create_invoice_title(
            _context(db),
            customer_id=101,
            invoice_title={
                "title_type": "COMPANY",
                "title": "越秀金融控股有限公司",
                "taxpayer_id": "91440000123456789X",
            },
            set_default=True,
        )

        assert result.success is True
        assert result.data["set_default"] is True
        assert fake_client.calls == [
            {
                "method": "POST",
                "path": "/v1/invoice-titles",
                "authorization": "Bearer test-token",
                "params": {"customer_id": 101},
                "json": {
                    "title_type": "COMPANY",
                    "title": "越秀金融控股有限公司",
                    "taxpayer_id": "91440000123456789X",
                },
            },
            {
                "method": "PATCH",
                "path": "/v1/invoice-titles/6001/set-default",
                "authorization": "Bearer test-token",
                "params": None,
                "json": None,
            },
        ]
        assert db.query(AgentToolCall).one().tool_name == "create_invoice_title"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_agent_tool_create_deployment_info_calls_existing_api():
    engine, db = _db_session()
    fake_client = FakeCRMAPIClient()
    service = CRMAgentToolService(api_client=fake_client)
    try:
        result = await service.create_deployment_info(
            _context(db),
            deployment_info={
                "customer_id": 101,
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
                "authorized_users": 100,
                "is_default": True,
            },
        )

        assert result.success is True
        assert result.data["id"] == 6101
        assert fake_client.calls == [{
            "method": "POST",
            "path": "/v1/deployment-infos/",
            "authorization": "Bearer test-token",
            "params": None,
            "json": {
                "customer_id": 101,
                "deployment_name": "生产环境",
                "server_address": "https://crm.example.com",
                "authorized_users": 100,
                "is_default": True,
            },
        }]
        assert db.query(AgentToolCall).one().tool_name == "create_deployment_info"
    finally:
        db.close()
        engine.dispose()
