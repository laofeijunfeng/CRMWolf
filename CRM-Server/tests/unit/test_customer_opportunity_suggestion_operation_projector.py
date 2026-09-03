from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent_async_operation import (
    AgentAsyncOperation,
    AgentAsyncOperationEvent,
    AgentAsyncOperationStatus,
)
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.services.customer_activity_contracts import CustomerActivitySuggestionJobStatus
from app.services.customer_opportunity_suggestion_operation_projector import (
    CustomerOpportunitySuggestionOperationProjector,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
            CustomerOpportunitySuggestionJob.__table__,
        ],
    )
    return engine, sessionmaker(bind=engine)()


def _job(status: str, result: dict | None = None, *, error: str | None = None):
    return CustomerOpportunitySuggestionJob(
        public_id="cosj_project_001",
        team_id=1,
        activity_id=241,
        activity_revision=1,
        submission_source="AGENT",
        status=status,
        attempt_count=1,
        run_id="run-project-001",
        graph_thread_id="thread-project-001",
        result_json=result,
        error_message=error,
        next_attempt_at=(
            datetime(2026, 9, 2, 10, 0) if status == CustomerActivitySuggestionJobStatus.RETRY_PENDING.value else None
        ),
        created_time=datetime(2026, 9, 1, 10, 0),
        updated_time=datetime(2026, 9, 1, 10, 1),
    )


def _operation(db, service, *, operation_key="customer-opportunity-suggestion:cosj_project_001"):
    return service.ensure_scheduled(
        db,
        operation_key=operation_key,
        request_id="cosj_project_001",
        team_id=1,
        user_id=2,
        session_id=3,
        source_user_message_id=11,
        source_assistant_message_id=12,
        operation_type="customer_opportunity_suggestion",
        resource_type="customer_activity",
        resource_id=241,
        resource_public_id="cosj_project_001",
        summary="正在分析是否需要推进商机",
    )


def test_completed_create_suggestion_waits_for_agent_user_continuation():
    engine, db = _session()
    try:
        service = AgentAsyncOperationService()
        projector = CustomerOpportunitySuggestionOperationProjector(operation_service=service)
        db.add(
            _job(
                CustomerActivitySuggestionJobStatus.COMPLETED.value,
                {
                    "success": True,
                    "decision": "CREATE_OPPORTUNITY",
                    "suggestion": {"title": "新商机", "execution_payload": {"amount": 100}},
                },
            )
        )
        db.commit()
        operation = _operation(db, service)
        projected = projector.project_request(
            db, team_id=1, request_id="cosj_project_001", operation_public_id=operation.public_id
        )
        db.commit()
        assert projected is not None
        assert projected.status == AgentAsyncOperationStatus.WAITING_USER
        assert projected.result_json["requires_user_action"] is True
        assert projected.result_json["continuation_kind"] == "create_opportunity"
        assert projected.result_json["suggestion"]["title"] == "新商机"
    finally:
        db.close()
        engine.dispose()


def test_high_confidence_existing_opportunity_is_silently_completed():
    engine, db = _session()
    try:
        service = AgentAsyncOperationService()
        projector = CustomerOpportunitySuggestionOperationProjector(operation_service=service)
        db.add(
            _job(
                CustomerActivitySuggestionJobStatus.COMPLETED.value,
                {
                    "success": True,
                    "decision": "NO_ACTION",
                    "silent_reason": "HIGH_CONFIDENCE_EXISTING_OPPORTUNITY",
                },
            )
        )
        db.commit()
        operation = _operation(db, service)
        projected = projector.project_request(
            db, team_id=1, request_id="cosj_project_001", operation_public_id=operation.public_id
        )
        db.commit()
        assert projected.status == AgentAsyncOperationStatus.SUCCEEDED
        assert projected.result_json["requires_user_action"] is False
        assert projected.summary == "已确认已有商机，无需重复创建"  # noqa: RUF001
    finally:
        db.close()
        engine.dispose()


def test_retry_pending_is_projected_without_marking_the_suggestion_succeeded():
    engine, db = _session()
    try:
        service = AgentAsyncOperationService()
        projector = CustomerOpportunitySuggestionOperationProjector(operation_service=service)
        db.add(
            _job(
                CustomerActivitySuggestionJobStatus.RETRY_PENDING.value,
                {"execution_status": "RETRY_PENDING"},
                error="模型暂时不可用",
            )
        )
        db.commit()
        operation = _operation(db, service)
        projected = projector.project_request(
            db, team_id=1, request_id="cosj_project_001", operation_public_id=operation.public_id
        )
        db.commit()
        assert projected.status == AgentAsyncOperationStatus.RETRY_SCHEDULED
        assert projected.error_message == "模型暂时不可用"
    finally:
        db.close()
        engine.dispose()


def test_deleted_source_is_cancelled_and_preserves_result_evidence():
    engine, db = _session()
    try:
        service = AgentAsyncOperationService()
        projector = CustomerOpportunitySuggestionOperationProjector(operation_service=service)
        db.add(
            _job(
                CustomerActivitySuggestionJobStatus.SKIPPED.value,
                {"skip_reason": "SOURCE_ACTIVITY_DELETED", "previous_error": "old"},
                error="SOURCE_ACTIVITY_DELETED",
            )
        )
        db.commit()
        operation = _operation(db, service)
        projected = projector.project_request(
            db, team_id=1, request_id="cosj_project_001", operation_public_id=operation.public_id
        )
        db.commit()
        assert projected.status == AgentAsyncOperationStatus.CANCELLED
        assert projected.result_json["skip_reason"] == "SOURCE_ACTIVITY_DELETED"
    finally:
        db.close()
        engine.dispose()
