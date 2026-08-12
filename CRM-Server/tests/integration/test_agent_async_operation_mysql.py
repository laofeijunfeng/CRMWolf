from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.models.agent_async_operation import AgentAsyncOperation, AgentAsyncOperationEvent
from app.services.agent.async_operation_service import AgentAsyncOperationService

pytestmark = pytest.mark.integration


def _mysql_integration_enabled() -> bool:
    return os.getenv("RUN_MYSQL_INTEGRATION") == "1" and engine.dialect.name == "mysql"


@pytest.mark.skipif(not _mysql_integration_enabled(), reason="requires RUN_MYSQL_INTEGRATION=1 and MySQL")
def test_ensure_scheduled_is_atomic_under_mysql_concurrency() -> None:
    service = AgentAsyncOperationService()
    suffix = uuid4().hex
    operation_key = f"integration:agent-async-operation:{suffix}"
    request_id = f"integration-request-{suffix}"
    worker_count = 4
    barrier = Barrier(worker_count)

    def schedule() -> tuple[int, str]:
        db = SessionLocal()
        try:
            isolation_level = str(db.execute(
                text("SELECT @@transaction_isolation")
            ).scalar_one())
            assert isolation_level.upper().replace("-", " ") == "REPEATABLE READ"
            barrier.wait(timeout=10)
            operation = service.ensure_scheduled(
                db,
                operation_key=operation_key,
                request_id=request_id,
                team_id=1,
                user_id=1,
                session_id=None,
                source_user_message_id=None,
                operation_type="customer_intelligence_refresh",
                resource_type="customer",
                summary="MySQL 并发幂等调度验证",
            )
            operation_id = int(operation.id)
            public_id = str(operation.public_id)
            db.commit()
            return operation_id, public_id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(lambda _: schedule(), range(worker_count)))

        assert len({operation_id for operation_id, _ in results}) == 1
        assert len({public_id for _, public_id in results}) == 1

        db = SessionLocal()
        try:
            operations = db.query(AgentAsyncOperation).filter(AgentAsyncOperation.operation_key == operation_key).all()
            assert len(operations) == 1
            events = (
                db.query(AgentAsyncOperationEvent)
                .filter(AgentAsyncOperationEvent.operation_id == operations[0].id)
                .order_by(AgentAsyncOperationEvent.sequence.asc())
                .all()
            )
            assert [(event.sequence, event.event_type) for event in events] == [(1, "SCHEDULED")]
            assert int(operations[0].next_event_sequence) == 2
        finally:
            db.close()
    finally:
        cleanup_db = SessionLocal()
        try:
            operation = (
                cleanup_db.query(AgentAsyncOperation)
                .filter(AgentAsyncOperation.operation_key == operation_key)
                .one_or_none()
            )
            if operation is not None:
                cleanup_db.delete(operation)
            cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
            raise
        finally:
            cleanup_db.close()
