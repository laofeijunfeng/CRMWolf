"""Late-binding tests for committed CRM durable work."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_async_operation import (
    AgentAsyncOperation,
    AgentAsyncOperationEvent,
    AgentAsyncOperationStatus,
)
from app.models.customer_activity_post_commit_job import (
    CustomerActivityPostCommitJob,
    CustomerActivityPostCommitJobStatus,
)
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.services.agent.durable_work import (
    AgentDurableWorkBinder,
    AgentDurableWorkRecoveryService,
)
from app.services.agent.durable_work_contracts import (
    AgentAsyncOperationBinding,
    CustomerActivityDurableWorkReceipt,
)
from app.services.customer_activity_post_commit_operation_projector import (
    CustomerActivityPostCommitOperationProjector,
)
from app.services.customer_opportunity_suggestion_operation_projector import (
    CustomerOpportunitySuggestionOperationProjector,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class _OriginService:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def ensure_from_bound_operation(self, db, *, operation):
        self.calls.append(operation)
        return SimpleNamespace(id=len(self.calls))


class _IntelligenceProjectionService:
    """Small projection double; the production service has its own lifecycle suite."""

    def __init__(self, operation_service: AgentAsyncOperationService) -> None:
        self.operation_service = operation_service
        self.calls: list[dict[str, object]] = []

    def bind_committed_event_to_agent(self, db, *, team_id, request_id, binding):
        if team_id != binding.team_id:
            raise ValueError("客户智能请求与 Agent 绑定团队不一致")
        self.calls.append({"team_id": team_id, "request_id": request_id, "binding": binding})
        operation = self.operation_service.bind_source(
            db,
            operation_key=f"customer-intelligence:{request_id}",
            request_id=request_id,
            team_id=binding.team_id,
            user_id=binding.user_id,
            session_id=binding.session_id,
            source_user_message_id=binding.source_user_message_id,
            source_assistant_message_id=binding.source_assistant_message_id,
            operation_type="customer_intelligence_refresh",
            resource_type="customer",
            resource_id=101,
            resource_public_id="cus_101",
            summary="客户档案后台更新",
        )
        projected = self.operation_service.complete(
            db,
            operation,
            degraded=False,
            summary="客户档案后台更新",
            result={"success": True},
        )
        return SimpleNamespace(operation_public_id=str(projected.public_id))


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
            CustomerActivityPostCommitJob.__table__,
            CustomerOpportunitySuggestionJob.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(AgentSession(id=3, session_key="session-3", team_id=1, user_id=2, title="跟进会话"))
    db.commit()
    return engine, db


def _job(*, team_id: int = 1, activity_id: int = 241) -> CustomerActivityPostCommitJob:
    return CustomerActivityPostCommitJob(
        public_id="pcj_async_001",
        team_id=team_id,
        activity_id=activity_id,
        activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
        status=CustomerActivityPostCommitJobStatus.COMPLETED,
        attempt_count=1,
        run_id="run-async-001",
        graph_thread_id="thread-async-001",
        result_json={"success": True, "activity_id": activity_id},
        created_time=datetime(2026, 8, 25, 10, 0),
        updated_time=datetime(2026, 8, 25, 10, 1),
        finished_at=datetime(2026, 8, 25, 10, 1),
    )


def _binding(*, team_id: int = 1) -> AgentAsyncOperationBinding:
    return AgentAsyncOperationBinding(
        team_id=team_id,
        user_id=2,
        session_id=3,
        source_user_message_id=1001,
        source_assistant_message_id=1002,
    )


def _receipt(*, activity_id: int = 241) -> CustomerActivityDurableWorkReceipt:
    return CustomerActivityDurableWorkReceipt(
        activity_id=activity_id,
        post_commit_job_public_id="pcj_async_001",
        customer_intelligence_request_id="cir_async_001",
    )





def test_customer_activity_receipt_requires_both_background_work_identities() -> None:
    with pytest.raises(ValueError, match="post_commit_job_public_id"):
        CustomerActivityDurableWorkReceipt(
            activity_id=241,
            customer_intelligence_request_id="cir_async_001",
        )

    with pytest.raises(ValueError, match="customer_intelligence_request_id"):
        CustomerActivityDurableWorkReceipt(
            activity_id=241,
            post_commit_job_public_id="pcj_async_001",
        )


def _turn_messages(db, *, receipt: CustomerActivityDurableWorkReceipt) -> tuple[int, int]:
    user_message = AgentMessage(
        team_id=1,
        user_id=2,
        session_id=3,
        role=AgentMessageRole.USER,
        content="记录客户跟进",
        turn_id="turn-durable-recovery",
        client_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        diagnostics_json={"request_input_fingerprint": "fingerprint"},
    )
    db.add(user_message)
    db.flush()
    assistant_message = AgentMessage(
        team_id=1,
        user_id=2,
        session_id=3,
        role=AgentMessageRole.ASSISTANT,
        content="已创建跟进",
        turn_id=user_message.turn_id,
        diagnostics_json={"durable_work": [receipt.model_dump(mode="json")]},
    )
    db.add(assistant_message)
    db.commit()
    return int(user_message.id), int(assistant_message.id)

def test_bind_projects_both_operations_to_the_exact_turn_and_is_idempotent() -> None:
    engine, db = _session()
    operation_service = AgentAsyncOperationService()
    intelligence_service = _IntelligenceProjectionService(operation_service)
    origin_service = _OriginService()
    binder = AgentDurableWorkBinder(
        operation_service=operation_service,
        post_commit_projector=CustomerActivityPostCommitOperationProjector(
            operation_service=operation_service
        ),
        intelligence_service=intelligence_service,
        activity_origin_service=origin_service,
    )
    try:
        db.add(_job())
        db.commit()

        binder.bind(db, receipts=[_receipt(), _receipt()], binding=_binding())
        db.commit()
        binder.bind(db, receipts=[_receipt()], binding=_binding())
        db.commit()

        operations = db.query(AgentAsyncOperation).order_by(AgentAsyncOperation.operation_type).all()
        assert len(operations) == 2
        assert {operation.operation_type for operation in operations} == {
            "customer_activity_post_commit",
            "customer_intelligence_refresh",
        }
        assert all(operation.session_id == 3 for operation in operations)
        assert all(operation.source_user_message_id == 1001 for operation in operations)
        assert all(operation.source_assistant_message_id == 1002 for operation in operations)
        assert all(operation.status == AgentAsyncOperationStatus.SUCCEEDED for operation in operations)
        assert len(intelligence_service.calls) == 2
        assert len(origin_service.calls) == 2
        assert all(operation.operation_type == "customer_activity_post_commit" for operation in origin_service.calls)
        assert all(operation.source_user_message_id == 1001 for operation in origin_service.calls)
        assert all(operation.source_assistant_message_id == 1002 for operation in origin_service.calls)
    finally:
        db.close()
        engine.dispose()



def test_recovery_recreates_both_operations_from_the_committed_assistant_receipt() -> None:
    engine, db = _session()
    operation_service = AgentAsyncOperationService()
    intelligence_service = _IntelligenceProjectionService(operation_service)
    origin_service = _OriginService()
    binder = AgentDurableWorkBinder(
        operation_service=operation_service,
        post_commit_projector=CustomerActivityPostCommitOperationProjector(
            operation_service=operation_service
        ),
        intelligence_service=intelligence_service,
        activity_origin_service=origin_service,
    )
    recovery = AgentDurableWorkRecoveryService(binder=binder)
    try:
        db.add(_job())
        db.commit()
        user_message_id, assistant_message_id = _turn_messages(db, receipt=_receipt())

        assert recovery.recover_session(db, team_id=1, user_id=2, session_id=3) == 1
        db.commit()

        operations = db.query(AgentAsyncOperation).order_by(AgentAsyncOperation.operation_type).all()
        assert {operation.operation_type for operation in operations} == {
            "customer_activity_post_commit",
            "customer_intelligence_refresh",
        }
        assert len(operations) == 2
        assert all(operation.source_user_message_id == user_message_id for operation in operations)
        assert all(operation.source_assistant_message_id == assistant_message_id for operation in operations)
        assert recovery.recover_session(db, team_id=1, user_id=2, session_id=3) == 0
        db.commit()
        assert db.query(AgentAsyncOperation).count() == 2
        assert len(intelligence_service.calls) == 1
    finally:
        db.close()
        engine.dispose()


def test_recovery_restores_the_missing_operation_without_duplicating_the_existing_one() -> None:
    engine, db = _session()
    operation_service = AgentAsyncOperationService()
    intelligence_service = _IntelligenceProjectionService(operation_service)
    origin_service = _OriginService()
    binder = AgentDurableWorkBinder(
        operation_service=operation_service,
        post_commit_projector=CustomerActivityPostCommitOperationProjector(
            operation_service=operation_service
        ),
        intelligence_service=intelligence_service,
        activity_origin_service=origin_service,
    )
    recovery = AgentDurableWorkRecoveryService(binder=binder)
    try:
        db.add(_job())
        db.commit()
        _turn_messages(db, receipt=_receipt())
        recovery.recover_session(db, team_id=1, user_id=2, session_id=3)
        db.commit()
        intelligence_operation = (
            db.query(AgentAsyncOperation)
            .filter(AgentAsyncOperation.operation_type == "customer_intelligence_refresh")
            .one()
        )
        db.delete(intelligence_operation)
        db.commit()

        assert recovery.recover_session(db, team_id=1, user_id=2, session_id=3) == 1
        db.commit()

        operations = db.query(AgentAsyncOperation).all()
        assert len(operations) == 2
        assert {operation.operation_type for operation in operations} == {
            "customer_activity_post_commit",
            "customer_intelligence_refresh",
        }
    finally:
        db.close()
        engine.dispose()


def test_recovery_never_reads_receipts_across_the_owned_session_boundary() -> None:
    engine, db = _session()
    recovery = AgentDurableWorkRecoveryService()
    try:
        db.add(_job())
        db.commit()
        _turn_messages(db, receipt=_receipt())

        assert recovery.recover_session(db, team_id=1, user_id=99, session_id=3) == 0
        assert recovery.recover_session(db, team_id=2, user_id=2, session_id=3) == 0
        assert db.query(AgentAsyncOperation).count() == 0
    finally:
        db.close()
        engine.dispose()

def test_bind_rejects_post_commit_receipt_for_another_activity() -> None:
    engine, db = _session()
    binder = AgentDurableWorkBinder()
    try:
        db.add(_job(activity_id=242))
        db.commit()

        with pytest.raises(ValueError, match="后提交任务与回执不匹配"):
            binder.bind(db, receipts=[_receipt(activity_id=241)], binding=_binding())
    finally:
        db.close()
        engine.dispose()


def test_bind_rejects_post_commit_job_from_another_team() -> None:
    engine, db = _session()
    binder = AgentDurableWorkBinder()
    try:
        db.add(_job(team_id=2))
        db.commit()

        with pytest.raises(ValueError, match="后提交任务不存在"):
            binder.bind(db, receipts=[_receipt()], binding=_binding(team_id=1))
    finally:
        db.close()
        engine.dispose()


def test_agent_receipt_binds_opportunity_suggestion_as_a_separate_operation() -> None:
    engine, db = _session()
    operation_service = AgentAsyncOperationService()
    intelligence_service = _IntelligenceProjectionService(operation_service)
    origin_service = _OriginService()
    binder = AgentDurableWorkBinder(
        operation_service=operation_service,
        post_commit_projector=CustomerActivityPostCommitOperationProjector(
            operation_service=operation_service
        ),
        opportunity_suggestion_projector=CustomerOpportunitySuggestionOperationProjector(
            operation_service=operation_service
        ),
        intelligence_service=intelligence_service,
        activity_origin_service=origin_service,
    )
    try:
        db.add(_job())
        db.add(
            CustomerOpportunitySuggestionJob(
                public_id="cosj_async_001",
                team_id=1,
                activity_id=241,
                activity_revision=1,
                submission_source="AGENT",
                status="COMPLETED",
                attempt_count=1,
                run_id="run-cosj-async-001",
                graph_thread_id="thread-cosj-async-001",
                result_json={
                    "success": True,
                    "decision": "CREATE_OPPORTUNITY",
                    "suggestion": {"title": "新商机"},
                },
            )
        )
        db.commit()
        receipt = CustomerActivityDurableWorkReceipt(
            activity_id=241,
            post_commit_job_public_id="pcj_async_001",
            customer_intelligence_request_id="cir_async_001",
            opportunity_suggestion_job_public_id="cosj_async_001",
        )
        binder.bind(db, receipts=[receipt], binding=_binding())
        db.commit()

        operations = db.query(AgentAsyncOperation).all()
        assert {operation.operation_type for operation in operations} == {
            "customer_activity_post_commit",
            "customer_intelligence_refresh",
            "customer_opportunity_suggestion",
        }
        suggestion_operation = next(
            operation for operation in operations
            if operation.operation_type == "customer_opportunity_suggestion"
        )
        assert suggestion_operation.status == AgentAsyncOperationStatus.WAITING_USER
        assert suggestion_operation.result_json["continuation_kind"] == "create_opportunity"
    finally:
        db.close()
        engine.dispose()
