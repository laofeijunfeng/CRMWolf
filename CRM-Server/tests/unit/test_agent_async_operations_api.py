from __future__ import annotations

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
from app.models.agent import AgentSession
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.utils.time import business_now


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_agent_session_operations_are_visible_after_original_stream_has_closed() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
            CustomerIntelligenceRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    service = AgentAsyncOperationService()
    try:
        session = AgentSession(session_key="session-1", team_id=1, user_id=2, title="跟进会话")
        db.add(session)
        db.commit()
        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:req-api",
            request_id="req-api",
            team_id=1,
            user_id=2,
            session_id=session.id,
            source_user_message_id=21,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
            summary="客户档案正在后台更新",
        )
        service.record_progress(
            db,
            operation,
            event_key="progress:context",
            step="load_customer_context",
            message="已读取客户上下文",
        )
        db.commit()

        app = FastAPI()
        app.include_router(agent_api.router)
        app.dependency_overrides[agent_api.get_db] = lambda: Session()
        app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
        app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(id=2)

        with TestClient(app) as client:
            response = client.get(f"/v1/agent/sessions/{session.id}/operations")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body[0]["public_id"] == operation.public_id
            assert body[0]["status"] == "QUEUED"
            assert body[0]["attempt_count"] == 0
            assert body[0]["events"][-1]["message"] == "已读取客户上下文"

            detail = client.get(f"/v1/agent/operations/{operation.public_id}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["request_id"] == "req-api"
    finally:
        db.close()
        engine.dispose()



def test_agent_operation_detail_repairs_terminal_customer_intelligence_projection() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
            CustomerIntelligenceRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    service = AgentAsyncOperationService()
    completed_at = business_now()
    try:
        session = AgentSession(session_key="session-repair", team_id=1, user_id=2, title="跟进会话")
        db.add(session)
        db.add(
            CustomerIntelligenceRun(
                run_key="terminal-api-repair-run",
                request_id="terminal-api-repair",
                event_key="terminal-api-repair-event",
                tenant_id=1,
                team_id=1,
                customer_id=18,
                actor_id="2",
                trigger_type="customer_activity_created",
                scope="brief",
                status=CustomerIntelligenceRunStatus.SUCCESS,
                attempt_count=1,
                max_attempts=3,
                started_time=completed_at,
                finished_time=completed_at,
                route="refresh_brief",
                result_json={"route": "refresh_brief", "degraded": False},
            )
        )
        db.commit()
        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:terminal-api-repair",
            request_id="terminal-api-repair",
            team_id=1,
            user_id=2,
            session_id=session.id,
            source_user_message_id=21,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
        )
        service.mark_running(db, operation)
        db.commit()

        app = FastAPI()
        app.include_router(agent_api.router)
        app.dependency_overrides[agent_api.get_db] = lambda: Session()
        app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
        app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(id=2)

        with TestClient(app) as client:
            detail = client.get(f"/v1/agent/operations/{operation.public_id}")

        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == "SUCCEEDED"
        assert detail.json()["finished_time"] is not None
    finally:
        db.close()
        engine.dispose()


def test_agent_operation_detail_exposes_projection_repair_failure(monkeypatch) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
            CustomerIntelligenceRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    service = AgentAsyncOperationService()
    try:
        session = AgentSession(session_key="session-repair-failure", team_id=1, user_id=2, title="跟进会话")
        db.add(session)
        db.commit()
        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:repair-failure",
            request_id="repair-failure",
            team_id=1,
            user_id=2,
            session_id=session.id,
            source_user_message_id=21,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
        )
        service.mark_running(db, operation)
        db.commit()

        def _raise_projection_failure(*args, **kwargs):
            raise RuntimeError("projection store unavailable")

        monkeypatch.setattr(
            agent_api.customer_intelligence_operation_projector,
            "project_request",
            _raise_projection_failure,
        )
        app = FastAPI()
        app.include_router(agent_api.router)
        app.dependency_overrides[agent_api.get_db] = lambda: Session()
        app.dependency_overrides[agent_api.get_current_user_team] = lambda: 1
        app.dependency_overrides[agent_api.get_current_active_user] = lambda: SimpleNamespace(id=2)

        with TestClient(app) as client:
            detail = client.get(f"/v1/agent/operations/{operation.public_id}")

        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["status"] == "RUNNING"
        assert body["error_message"] == "projection store unavailable"
        assert body["events"][-1]["message"] == "后台状态同步异常。系统将自动恢复。"
    finally:
        db.close()
        engine.dispose()
