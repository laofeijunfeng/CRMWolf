"""Regression tests for DEF-2026-0818-001.

Agent create_customer_activity must treat activity persistence as success.
Post-commit matching stays on the existing async outbox and must not decide
the write result.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentIdempotencyKey, AgentIdempotencyStatus, AgentSession, AgentToolCall
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
from app.services.agent.tools.base import AgentToolContext
from app.services.agent.tools.service import CRMAgentToolService

CUSTOMER_PUBLIC_ID = "cus_test_101"
SOURCE_CONTENT = "微信联系余贝霆，确认放款进度。"


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


class _RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def request(self, method, path, authorization, *, params=None, json=None, idempotency_key=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "authorization": authorization,
                "params": params,
                "json": json,
                "idempotency_key": idempotency_key,
            }
        )
        return {
            "id": 241,
            "customer_id": CUSTOMER_PUBLIC_ID,
            "activity_kind": json["activity_kind"],
            "source_content": json["source_content"],
            "durable_work": {
                "post_commit_job_public_id": "pcj_async_001",
                "customer_intelligence_request_id": None,
            },
        }


class _TimeoutAfterWriteClient(_RecordingClient):
    def __init__(self, *, persisted: bool) -> None:
        super().__init__()
        self.persisted = persisted

    async def request(self, method, path, authorization, *, params=None, json=None, idempotency_key=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "authorization": authorization,
                "params": params,
                "json": json,
                "idempotency_key": idempotency_key,
            }
        )
        if method == "POST":
            raise httpx.ReadTimeout("")
        if method == "GET" and path == f"/v1/customer-activities/{CUSTOMER_PUBLIC_ID}":
            if not self.persisted:
                return []
            return [
                {
                    "id": 241,
                    "customer_id": CUSTOMER_PUBLIC_ID,
                    "activity_kind": "WECHAT_FOLLOW_UP",
                    "source_content": SOURCE_CONTENT,
                }
            ]
        raise AssertionError(f"unexpected request {method} {path}")


def _db_session(extra_tables=None):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        AgentSession.__table__,
        AgentToolCall.__table__,
        AgentIdempotencyKey.__table__,
    ]
    if extra_tables:
        tables.extend(extra_tables)
    Base.metadata.create_all(engine, tables=tables)
    session = sessionmaker(bind=engine)()
    session.add(AgentSession(id=3, session_key="session-3", team_id=1, user_id=2, title="跟进会话"))
    session.commit()
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
async def test_create_customer_activity_uses_async_post_commit():
    engine, db = _db_session()
    client = _RecordingClient()
    service = CRMAgentToolService(api_client=client)
    try:
        result = await service.create_customer_activity(
            _context(db),
            customer_id=CUSTOMER_PUBLIC_ID,
            activity_kind="WECHAT_FOLLOW_UP",
            source_content=SOURCE_CONTENT,
            title="确认放款进度",
            idempotency_suffix="msg-async",
        )

        assert result.success is True
        assert client.calls[0]["params"] == {"post_commit_mode": "async"}
        assert client.calls[0]["method"] == "POST"
        assert db.query(AgentIdempotencyKey).one().status == AgentIdempotencyStatus.SUCCESS
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_create_customer_activity_timeout_after_write_reconciles_to_success():
    engine, db = _db_session()
    client = _TimeoutAfterWriteClient(persisted=True)
    service = CRMAgentToolService(api_client=client)
    try:
        result = await service.create_customer_activity(
            _context(db),
            customer_id=CUSTOMER_PUBLIC_ID,
            activity_kind="WECHAT_FOLLOW_UP",
            source_content=SOURCE_CONTENT,
            idempotency_suffix="msg-timeout-success",
        )

        assert result.success is True
        assert result.error_message is None
        assert result.data["id"] == 241
        assert result.data["source_content"] == SOURCE_CONTENT
        assert [call["method"] for call in client.calls] == ["POST", "GET"]
        idempotency = db.query(AgentIdempotencyKey).one()
        assert idempotency.status == AgentIdempotencyStatus.SUCCESS
        assert idempotency.error_message is None
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_create_customer_activity_timeout_without_row_stays_ambiguous():
    engine, db = _db_session()
    client = _TimeoutAfterWriteClient(persisted=False)
    service = CRMAgentToolService(api_client=client)
    try:
        result = await service.create_customer_activity(
            _context(db),
            customer_id=CUSTOMER_PUBLIC_ID,
            activity_kind="WECHAT_FOLLOW_UP",
            source_content=SOURCE_CONTENT,
            idempotency_suffix="msg-timeout-missing",
        )

        assert result.success is False
        assert result.error_message == "ReadTimeout"
        assert db.query(AgentIdempotencyKey).one().status == AgentIdempotencyStatus.AMBIGUOUS
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_create_customer_activity_binds_post_commit_async_operation():
    engine, db = _db_session(extra_tables=[AgentAsyncOperation.__table__, AgentAsyncOperationEvent.__table__])
    client = _RecordingClient()
    service = CRMAgentToolService(api_client=client)
    try:
        result = await service.create_customer_activity(
            _context(db),
            customer_id=CUSTOMER_PUBLIC_ID,
            activity_kind="WECHAT_FOLLOW_UP",
            source_content=SOURCE_CONTENT,
            idempotency_suffix="msg-bind",
        )

        assert result.success is True
        operation = db.query(AgentAsyncOperation).one()
        assert operation.operation_type == "customer_activity_post_commit"
        assert operation.request_id == "pcj_async_001"
        assert operation.session_id == 3
        assert operation.resource_id == 241
        assert operation.status == "QUEUED"
        assert "已记录" in (operation.summary or "")
    finally:
        db.close()
        engine.dispose()
