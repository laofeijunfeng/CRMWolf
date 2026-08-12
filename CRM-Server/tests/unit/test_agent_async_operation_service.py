from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentSession
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.utils.time import business_now


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session_factory():
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
        ],
    )
    return engine, sessionmaker(bind=engine)


def test_operation_lifecycle_is_durable_replayable_and_idempotent() -> None:
    engine, Session = _session_factory()
    service = AgentAsyncOperationService()
    db = Session()
    try:
        session = AgentSession(
            session_key="session-1",
            team_id=1,
            user_id=2,
            title="跟进会话",
        )
        db.add(session)
        db.commit()

        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:req-1",
            request_id="req-1",
            team_id=1,
            user_id=2,
            session_id=session.id,
            source_user_message_id=11,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
            summary="客户档案正在后台更新",
        )
        db.commit()

        same_operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:req-1",
            request_id="req-1",
            team_id=1,
            user_id=2,
            session_id=session.id,
            source_user_message_id=11,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
            summary="客户档案正在后台更新",
        )
        service.mark_running(db, operation, graph_thread_id="crm-agent-ci:1:2:1:event-1")
        service.record_progress(
            db,
            operation,
            event_key="progress:extract-facts",
            step="extract_customer_facts",
            message="已提炼 6 条客户事实",
            payload={"persisted_fact_count": 6},
        )
        service.record_progress(
            db,
            operation,
            event_key="progress:extract-facts",
            step="extract_customer_facts",
            message="已提炼 6 条客户事实",
            payload={"persisted_fact_count": 6},
        )
        service.complete(
            db,
            operation,
            degraded=True,
            summary="客户档案已更新。AI 增强暂不可用。已自动降级",
            result={"persisted_fact_count": 6, "degraded": True},
        )
        db.commit()

        assert same_operation.id == operation.id
        projection = service.get_projection(
            db,
            team_id=1,
            user_id=2,
            public_id=operation.public_id,
        )
        assert projection is not None
        assert projection.status == "DEGRADED"
        assert projection.session_id == session.id
        assert projection.graph_thread_id == "crm-agent-ci:1:2:1:event-1"
        assert projection.result["persisted_fact_count"] == 6
        assert [event.event_type for event in projection.events] == [
            "SCHEDULED",
            "STARTED",
            "PROGRESS",
            "DEGRADED",
        ]
        assert [event.sequence for event in projection.events] == [1, 2, 3, 4]
    finally:
        db.close()
        engine.dispose()


def test_operation_retry_attempts_keep_distinct_lifecycle_events() -> None:
    engine, Session = _session_factory()
    service = AgentAsyncOperationService()
    db = Session()
    try:
        session = AgentSession(session_key="session-retry", team_id=1, user_id=2, title="重试会话")
        db.add(session)
        db.commit()
        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:req-retry",
            request_id="req-retry",
            team_id=1,
            user_id=2,
            session_id=session.id,
            source_user_message_id=11,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
        )
        service.mark_running(db, operation)
        service.fail(
            db,
            operation,
            error_message="temporary failure",
            retry_at=business_now() + timedelta(minutes=1),
        )
        service.mark_running(db, operation)
        service.record_progress(
            db,
            operation,
            event_key="graph-progress:2:1:extract:ok",
            step="extract",
            message="第二次尝试正在提炼客户事实",
        )
        service.complete(db, operation, degraded=False, summary="客户档案已更新")
        db.commit()

        projection = service.get_projection(db, team_id=1, user_id=2, public_id=operation.public_id)
        assert projection is not None
        assert projection.attempt_count == 2
        assert [event.event_type for event in projection.events] == [
            "SCHEDULED",
            "STARTED",
            "RETRY_SCHEDULED",
            "STARTED",
            "PROGRESS",
            "SUCCEEDED",
        ]
        assert [event.sequence for event in projection.events] == [1, 2, 3, 4, 5, 6]
    finally:
        db.close()
        engine.dispose()


def test_failure_recovery_does_not_regress_a_completed_operation() -> None:
    engine, Session = _session_factory()
    service = AgentAsyncOperationService()
    db = Session()
    try:
        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:req-complete-before-recovery",
            request_id="req-complete-before-recovery",
            team_id=1,
            user_id=2,
            session_id=None,
            source_user_message_id=None,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
        )
        service.mark_running(db, operation)
        service.complete(
            db,
            operation,
            degraded=False,
            summary="Customer profile updated",
            result={"persisted_fact_count": 6},
        )
        service.fail(
            db,
            operation,
            error_message="stale recovery arrived after completion",
            retry_at=business_now() + timedelta(minutes=1),
        )
        db.commit()

        projection = service.get_projection(db, team_id=1, user_id=2, public_id=operation.public_id)
        assert projection is not None
        assert projection.status == "SUCCEEDED"
        assert projection.result == {"persisted_fact_count": 6}
        assert [event.event_type for event in projection.events] == [
            "SCHEDULED",
            "STARTED",
            "SUCCEEDED",
        ]
    finally:
        db.close()
        engine.dispose()


def test_operation_cancellation_is_terminal_and_idempotent() -> None:
    engine, Session = _session_factory()
    service = AgentAsyncOperationService()
    db = Session()
    try:
        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:req-cancel",
            request_id="req-cancel",
            team_id=1,
            user_id=2,
            session_id=None,
            source_user_message_id=None,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
        )
        service.mark_running(db, operation)
        service.cancel(
            db,
            operation,
            summary="Newer customer profile exists; background operation cancelled",
            result={"reason": "customer_brief_already_available"},
        )
        service.cancel(
            db,
            operation,
            summary="不应覆盖首次取消结果",
            result={"reason": "duplicate"},
        )
        db.commit()

        projection = service.get_projection(db, team_id=1, user_id=2, public_id=operation.public_id)
        assert projection is not None
        assert projection.status == "CANCELLED"
        assert projection.summary == "Newer customer profile exists; background operation cancelled"
        assert projection.result == {"reason": "customer_brief_already_available"}
        assert projection.error_message is None
        assert projection.next_retry_at is None
        assert projection.finished_time is not None
        assert [event.event_type for event in projection.events] == [
            "SCHEDULED",
            "STARTED",
            "CANCELLED",
        ]
    finally:
        db.close()
        engine.dispose()


def test_cancelled_operation_ignores_late_worker_start_and_completion() -> None:
    engine, Session = _session_factory()
    service = AgentAsyncOperationService()
    db = Session()
    try:
        operation = service.ensure_scheduled(
            db,
            operation_key="customer-intelligence:req-cancel-race",
            request_id="req-cancel-race",
            team_id=1,
            user_id=2,
            session_id=None,
            source_user_message_id=None,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=18,
        )
        service.mark_running(db, operation)
        service.cancel(
            db,
            operation,
            summary="Historical backfill no longer required",
            result={"reason": "customer_brief_already_available"},
        )
        service.mark_running(db, operation, summary="Late worker started")
        service.record_progress(
            db,
            operation,
            event_key="late-progress",
            step="late_step",
            message="Late worker progress",
        )
        service.complete(
            db,
            operation,
            degraded=False,
            summary="Late worker completed",
            result={"persisted_fact_count": 9},
        )
        db.commit()

        projection = service.get_projection(db, team_id=1, user_id=2, public_id=operation.public_id)
        assert projection is not None
        assert projection.status == "CANCELLED"
        assert projection.summary == "Historical backfill no longer required"
        assert projection.result == {"reason": "customer_brief_already_available"}
        assert projection.attempt_count == 1
        assert [event.event_type for event in projection.events] == [
            "SCHEDULED",
            "STARTED",
            "CANCELLED",
        ]
    finally:
        db.close()
        engine.dispose()


def test_request_lookup_is_scoped_by_team() -> None:
    engine, Session = _session_factory()
    service = AgentAsyncOperationService()
    db = Session()
    try:
        first_session = AgentSession(session_key="session-team-1", team_id=1, user_id=2, title="团队一")
        second_session = AgentSession(session_key="session-team-2", team_id=9, user_id=8, title="团队二")
        db.add_all([first_session, second_session])
        db.commit()
        first = service.ensure_scheduled(
            db,
            operation_key="team-1-operation",
            request_id="shared-request",
            team_id=1,
            user_id=2,
            session_id=first_session.id,
            source_user_message_id=None,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
        )
        second = service.ensure_scheduled(
            db,
            operation_key="team-9-operation",
            request_id="shared-request",
            team_id=9,
            user_id=8,
            session_id=second_session.id,
            source_user_message_id=None,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
        )
        db.commit()

        assert service.get_by_request_id(db, team_id=1, request_id="shared-request").id == first.id
        assert service.get_by_request_id(db, team_id=9, request_id="shared-request").id == second.id
        assert service.get_by_request_id(db, team_id=7, request_id="shared-request") is None
    finally:
        db.close()
        engine.dispose()


def test_session_projection_returns_latest_window_in_display_order() -> None:
    engine, Session = _session_factory()
    service = AgentAsyncOperationService()
    db = Session()
    try:
        session = AgentSession(session_key="session-latest", team_id=1, user_id=2, title="最新任务")
        db.add(session)
        db.commit()
        for index in range(3):
            service.ensure_scheduled(
                db,
                operation_key=f"operation-{index}",
                request_id=f"request-{index}",
                team_id=1,
                user_id=2,
                session_id=session.id,
                source_user_message_id=index,
                operation_type="customer_intelligence_refresh",
                resource_type="customer",
            )
            db.commit()

        projections = service.list_session_projections(
            db,
            team_id=1,
            user_id=2,
            session_id=session.id,
            limit=2,
        )
        assert [projection.request_id for projection in projections] == ["request-1", "request-2"]
    finally:
        db.close()
        engine.dispose()
