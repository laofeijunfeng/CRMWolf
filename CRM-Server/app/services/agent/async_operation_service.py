"""Durable projection service for asynchronous Agent operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError

from app.models.agent_async_operation import (
    AgentAsyncOperation,
    AgentAsyncOperationEvent,
    AgentAsyncOperationStatus,
)
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.services.agent.types import coerce_json_dict
from app.services.customer_activity_agent_origin_service import customer_activity_agent_origin_service
from app.utils.time import business_now

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

JSONDict: TypeAlias = dict[str, object]
TERMINAL_OPERATION_STATUSES = frozenset({
    AgentAsyncOperationStatus.SUCCEEDED,
    AgentAsyncOperationStatus.DEGRADED,
    AgentAsyncOperationStatus.FAILED,
    AgentAsyncOperationStatus.CANCELLED,
})


@dataclass(frozen=True)
class AgentAsyncOperationEventProjection:
    sequence: int
    event_type: str
    status: str
    event_key: str
    step: str | None
    message: str | None
    payload: JSONDict
    occurred_at: datetime


@dataclass(frozen=True)
class AgentAsyncOperationProjection:
    public_id: str
    request_id: str
    team_id: int
    user_id: int
    session_id: int | None
    source_user_message_id: int | None
    source_assistant_message_id: int | None
    operation_type: str
    resource_type: str
    resource_id: int | None
    resource_public_id: str | None
    status: str
    summary: str | None
    current_step: str | None
    graph_thread_id: str | None
    result: JSONDict
    error_message: str | None
    started_time: datetime | None
    finished_time: datetime | None
    next_retry_at: datetime | None
    attempt_count: int
    created_time: datetime
    updated_time: datetime
    events: tuple[AgentAsyncOperationEventProjection, ...]


class AgentAsyncOperationService:
    def bind_source(
        self,
        db: Session,
        *,
        operation_key: str,
        request_id: str,
        team_id: int,
        user_id: int,
        session_id: int,
        source_user_message_id: int | None,
        source_assistant_message_id: int | None,
        operation_type: str,
        resource_type: str,
        resource_id: int,
        resource_public_id: str | None = None,
        graph_thread_id: str | None = None,
        summary: str = "客户档案后台更新",
    ) -> AgentAsyncOperation:
        """Idempotently bind durable work to its exact Agent source messages.

        Source binding is independent from lifecycle projection, so a run that
        already reached a terminal state can still be attached to the original
        turn without resetting or re-executing the work.
        """

        operation = self.ensure_scheduled(
            db,
            operation_key=operation_key,
            request_id=request_id,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            source_user_message_id=source_user_message_id,
            source_assistant_message_id=source_assistant_message_id,
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_public_id=resource_public_id,
            summary=summary,
            graph_thread_id=graph_thread_id,
        )
        locked = self._lock_operation(db, operation.id)
        self._validate_binding_identity(
            locked,
            operation_key=operation_key,
            request_id=request_id,
            team_id=team_id,
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        for field, value in (
            ("user_id", user_id),
            ("session_id", session_id),
            ("source_user_message_id", source_user_message_id),
            ("source_assistant_message_id", source_assistant_message_id),
            ("resource_public_id", resource_public_id),
            ("graph_thread_id", graph_thread_id),
        ):
            current = getattr(locked, field)
            if current is not None and value is not None and str(current) != str(value):
                raise ValueError(f"异步操作来源绑定冲突: {field}")
            if current is None and value is not None:
                setattr(locked, field, value)
        if not locked.summary:
            locked.summary = summary
        db.flush()
        return locked

    def latest_session_user_message_id(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        created_at_or_before: datetime | None = None,
    ) -> int | None:
        """Return the latest user message that can own this session's async work."""

        from app.models.agent import AgentMessage, AgentMessageRole

        try:
            query = db.query(AgentMessage).filter(
                AgentMessage.team_id == team_id,
                AgentMessage.user_id == user_id,
                AgentMessage.session_id == session_id,
                AgentMessage.role == AgentMessageRole.USER,
            )
            if created_at_or_before is not None:
                query = query.filter(AgentMessage.created_time <= created_at_or_before)
            message = query.order_by(AgentMessage.created_time.desc(), AgentMessage.id.desc()).first()
        except Exception:
            return None
        return int(message.id) if message is not None else None

    def bind_customer_activity_post_commit_assistant_message(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        source_user_message_id: int,
        source_assistant_message_id: int,
    ) -> int:
        """Late-bind the persisted assistant message onto this turn's reconciliation cards."""

        operations = (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == team_id,
                AgentAsyncOperation.user_id == user_id,
                AgentAsyncOperation.session_id == session_id,
                AgentAsyncOperation.operation_type == "customer_activity_post_commit",
                AgentAsyncOperation.source_user_message_id == source_user_message_id,
                AgentAsyncOperation.source_assistant_message_id.is_(None),
            )
            .all()
        )
        for operation in operations:
            bound_operation = self.bind_source(
                db,
                operation_key=str(operation.operation_key),
                request_id=str(operation.request_id),
                team_id=int(operation.team_id),
                user_id=int(operation.user_id),
                session_id=int(operation.session_id),
                source_user_message_id=source_user_message_id,
                source_assistant_message_id=source_assistant_message_id,
                operation_type=str(operation.operation_type),
                resource_type=str(operation.resource_type),
                resource_id=int(operation.resource_id) if operation.resource_id is not None else 0,
                resource_public_id=(
                    str(operation.resource_public_id) if operation.resource_public_id is not None else None
                ),
                graph_thread_id=(
                    str(operation.graph_thread_id) if operation.graph_thread_id is not None else None
                ),
                summary=str(operation.summary) if operation.summary else "跟进已记录，任务对账处理中",
            )
            customer_activity_agent_origin_service.ensure_from_bound_operation(
                db,
                operation=bound_operation,
            )
        return len(operations)

    def repair_unanchored_customer_activity_post_commit_sources(
        self,
        db: Session,
        operations: list[AgentAsyncOperationProjection],
    ) -> bool:
        """Attach legacy reconciliation cards to the originating user turn."""

        targets = [
            operation
            for operation in operations
            if (
                operation.operation_type == "customer_activity_post_commit"
                and operation.session_id is not None
                and operation.source_user_message_id is None
            )
        ]
        if not targets:
            return False

        repaired = False
        for operation in targets:
            source_user_message_id = self.latest_session_user_message_id(
                db,
                team_id=operation.team_id,
                user_id=operation.user_id,
                session_id=int(operation.session_id),
                created_at_or_before=operation.created_time,
            )
            if source_user_message_id is None:
                continue
            persisted = (
                db.query(AgentAsyncOperation)
                .filter(AgentAsyncOperation.public_id == operation.public_id)
                .one_or_none()
            )
            if persisted is None or persisted.session_id is None:
                continue
            self.bind_source(
                db,
                operation_key=str(persisted.operation_key),
                request_id=str(persisted.request_id),
                team_id=int(persisted.team_id),
                user_id=int(persisted.user_id),
                session_id=int(persisted.session_id),
                source_user_message_id=source_user_message_id,
                source_assistant_message_id=(
                    int(persisted.source_assistant_message_id)
                    if persisted.source_assistant_message_id is not None
                    else None
                ),
                operation_type=str(persisted.operation_type),
                resource_type=str(persisted.resource_type),
                resource_id=int(persisted.resource_id) if persisted.resource_id is not None else 0,
                resource_public_id=(
                    str(persisted.resource_public_id) if persisted.resource_public_id is not None else None
                ),
                graph_thread_id=(
                    str(persisted.graph_thread_id) if persisted.graph_thread_id is not None else None
                ),
                summary=str(persisted.summary) if persisted.summary else "跟进已记录，任务对账处理中",
            )
            repaired = True
        if repaired:
            db.commit()
        return repaired

    def project_customer_intelligence_run(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        run: CustomerIntelligenceRun,
    ) -> AgentAsyncOperation:
        """Project the durable run snapshot into the user-facing operation."""

        locked = self._lock_operation(db, operation.id)
        if int(locked.team_id) != int(run.team_id) or str(locked.request_id) != str(run.request_id):
            raise ValueError("客户智能运行与异步操作不匹配")
        if locked.resource_id is not None and int(locked.resource_id) != int(run.customer_id):
            raise ValueError("客户智能运行与异步操作客户不匹配")

        run_status = str(run.status)
        status_by_run = {
            CustomerIntelligenceRunStatus.PENDING: AgentAsyncOperationStatus.QUEUED,
            CustomerIntelligenceRunStatus.RUNNING: AgentAsyncOperationStatus.RUNNING,
            CustomerIntelligenceRunStatus.RETRY_PENDING: AgentAsyncOperationStatus.RETRY_SCHEDULED,
            CustomerIntelligenceRunStatus.FAILED: AgentAsyncOperationStatus.FAILED,
            CustomerIntelligenceRunStatus.CANCELLED: AgentAsyncOperationStatus.CANCELLED,
        }
        result = coerce_json_dict(run.result_json)
        degraded = result.get("degraded") is True
        projected_status = (
            AgentAsyncOperationStatus.DEGRADED
            if run_status == CustomerIntelligenceRunStatus.SUCCESS and degraded
            else AgentAsyncOperationStatus.SUCCEEDED
            if run_status == CustomerIntelligenceRunStatus.SUCCESS
            else status_by_run.get(run_status, AgentAsyncOperationStatus.QUEUED)
        )
        locked.status = projected_status
        locked.attempt_count = int(run.attempt_count or 0)
        locked.started_time = run.started_time
        locked.finished_time = run.finished_time if projected_status in TERMINAL_OPERATION_STATUSES else None
        locked.next_retry_at = run.next_retry_at
        locked.error_message = str(run.error_message)[:2000] if run.error_message else None
        if run_status == CustomerIntelligenceRunStatus.SUCCESS:
            locked.summary = "客户档案后台更新"
            locked.result_json = result
        elif run_status in {
            CustomerIntelligenceRunStatus.RUNNING,
            CustomerIntelligenceRunStatus.RETRY_PENDING,
        }:
            locked.summary = "客户档案后台更新"
        elif run_status == CustomerIntelligenceRunStatus.FAILED:
            locked.summary = "客户档案后台更新失败"
        elif run_status == CustomerIntelligenceRunStatus.CANCELLED:
            locked.summary = "客户档案后台更新已取消"
        else:
            locked.summary = locked.summary or "客户档案后台更新"

        for index, item in enumerate(run.visible_trace_json or []):
            trace = coerce_json_dict(item)
            message = str(trace.get("content") or trace.get("message") or "").strip()
            step = str(trace.get("title") or trace.get("step") or "customer_intelligence").strip()
            if not message:
                continue
            self._append_event(
                db,
                locked,
                event_key=f"customer-intelligence-run:{int(run.id)}:trace:{index}",
                event_type="PROGRESS",
                status=projected_status,
                step=step,
                message=message,
                payload=trace,
                occurred_at=run.finished_time or run.started_time,
            )
            locked.current_step = step

        lifecycle_type = {
            AgentAsyncOperationStatus.QUEUED: "SCHEDULED",
            AgentAsyncOperationStatus.RUNNING: "STARTED",
            AgentAsyncOperationStatus.RETRY_SCHEDULED: "RETRY_SCHEDULED",
            AgentAsyncOperationStatus.SUCCEEDED: "SUCCEEDED",
            AgentAsyncOperationStatus.DEGRADED: "DEGRADED",
            AgentAsyncOperationStatus.FAILED: "FAILED",
            AgentAsyncOperationStatus.CANCELLED: "CANCELLED",
        }[projected_status]
        self._append_event(
            db,
            locked,
            event_key=f"customer-intelligence-run:{int(run.id)}:lifecycle:{run_status}:{int(run.attempt_count or 0)}",
            event_type=lifecycle_type,
            status=projected_status,
            step=locked.current_step,
            message=locked.summary,
            payload={
                "run_id": int(run.id),
                "run_status": run_status,
                "next_retry_at": run.next_retry_at.isoformat() if run.next_retry_at else None,
            },
            occurred_at=run.finished_time or run.started_time,
        )
        db.flush()
        return locked

    def ensure_scheduled(
        self,
        db: Session,
        *,
        operation_key: str,
        request_id: str,
        team_id: int,
        user_id: int,
        session_id: int | None,
        source_user_message_id: int | None,
        operation_type: str,
        resource_type: str,
        resource_id: int | None = None,
        resource_public_id: str | None = None,
        source_assistant_message_id: int | None = None,
        summary: str | None = None,
        graph_thread_id: str | None = None,
    ) -> AgentAsyncOperation:
        values = {
            "public_id": f"aop_{uuid4().hex}",
            "operation_key": operation_key,
            "request_id": request_id,
            "team_id": team_id,
            "user_id": user_id,
            "session_id": session_id,
            "source_user_message_id": source_user_message_id,
            "source_assistant_message_id": source_assistant_message_id,
            "operation_type": operation_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_public_id": resource_public_id,
            "status": AgentAsyncOperationStatus.QUEUED,
            "summary": summary,
            "graph_thread_id": graph_thread_id,
            "attempt_count": 0,
            "next_event_sequence": 1,
        }
        if db.get_bind().dialect.name == "mysql":
            operation = self._ensure_scheduled_mysql(
                db,
                team_id=team_id,
                operation_key=operation_key,
                values=values,
            )
        else:
            operation = self._get_by_key(db, team_id=team_id, operation_key=operation_key)
            if operation is None:
                candidate = AgentAsyncOperation(**values)
                try:
                    with db.begin_nested():
                        db.add(candidate)
                        db.flush()
                    operation = candidate
                except IntegrityError:
                    operation = self._get_by_key(db, team_id=team_id, operation_key=operation_key)
                    if operation is None:
                        raise
        locked_operation = self._lock_operation(db, operation.id)
        self._append_event(
            db,
            locked_operation,
            event_key="lifecycle:scheduled",
            event_type="SCHEDULED",
            status=AgentAsyncOperationStatus.QUEUED,
            message=summary,
        )
        return locked_operation

    def mark_running(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        *,
        graph_thread_id: str | None = None,
        summary: str | None = None,
    ) -> AgentAsyncOperation:
        locked_operation = self._lock_operation(db, operation.id)
        if str(locked_operation.status) in TERMINAL_OPERATION_STATUSES:
            return locked_operation
        next_attempt = int(locked_operation.attempt_count or 0) + 1
        locked_operation.attempt_count = next_attempt
        locked_operation.status = AgentAsyncOperationStatus.RUNNING
        locked_operation.started_time = locked_operation.started_time or business_now()
        locked_operation.finished_time = None
        locked_operation.next_retry_at = None
        locked_operation.error_message = None
        if graph_thread_id:
            locked_operation.graph_thread_id = graph_thread_id
        if summary:
            locked_operation.summary = summary
        self._append_event(
            db,
            locked_operation,
            event_key=f"lifecycle:started:{next_attempt}",
            event_type="STARTED",
            status=AgentAsyncOperationStatus.RUNNING,
            message=summary or "后台任务已开始执行",
        )
        db.flush()
        return locked_operation

    def record_progress(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        *,
        event_key: str,
        step: str,
        message: str,
        payload: JSONDict | None = None,
        occurred_at: datetime | None = None,
    ) -> AgentAsyncOperationEvent | None:
        locked_operation = self._lock_operation(db, operation.id)
        if str(locked_operation.status) in TERMINAL_OPERATION_STATUSES:
            return None
        event = self._append_event(
            db,
            locked_operation,
            event_key=event_key,
            event_type="PROGRESS",
            status=str(locked_operation.status or AgentAsyncOperationStatus.RUNNING),
            step=step,
            message=message,
            payload=payload,
            occurred_at=occurred_at,
        )
        if event is not None:
            locked_operation.current_step = step
            locked_operation.summary = message
            db.flush()
        return event

    def record_projection_warning(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        *,
        run_id: int,
        run_status: str,
        error_message: str,
    ) -> AgentAsyncOperationEvent | None:
        """Expose a retriable UI-projection failure without failing the run.

        The durable customer-intelligence run remains authoritative. This event
        prevents a projection outage from looking like an unexplained spinner;
        a later projection or read-repair clears ``error_message`` and converges
        the operation to the run snapshot.
        """

        locked_operation = self._lock_operation(db, operation.id)
        if str(locked_operation.status) in TERMINAL_OPERATION_STATUSES:
            return None
        message = "后台状态同步异常。系统将自动恢复。"
        locked_operation.error_message = error_message[:2000]
        event = self._append_event(
            db,
            locked_operation,
            event_key=f"projection-warning:{run_id}:{run_status}",
            event_type="PROGRESS",
            status=str(locked_operation.status or AgentAsyncOperationStatus.RUNNING),
            step="projection_sync",
            message=message,
            payload={
                "run_id": run_id,
                "run_status": run_status,
                "error": error_message[:2000],
            },
        )
        if event is not None:
            locked_operation.current_step = "projection_sync"
            locked_operation.summary = message
        db.flush()
        return event

    def complete(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        *,
        degraded: bool,
        summary: str,
        result: JSONDict | None = None,
    ) -> AgentAsyncOperation:
        locked_operation = self._lock_operation(db, operation.id)
        if str(locked_operation.status) in TERMINAL_OPERATION_STATUSES:
            return locked_operation
        status = AgentAsyncOperationStatus.DEGRADED if degraded else AgentAsyncOperationStatus.SUCCEEDED
        locked_operation.status = status
        locked_operation.summary = summary
        locked_operation.result_json = result or {}
        locked_operation.error_message = None
        locked_operation.next_retry_at = None
        locked_operation.finished_time = business_now()
        self._append_event(
            db,
            locked_operation,
            event_key=f"lifecycle:{status.lower()}",
            event_type=status,
            status=status,
            step=locked_operation.current_step,
            message=summary,
            payload=result,
        )
        db.flush()
        return locked_operation

    def fail(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        *,
        error_message: str,
        retry_at: datetime | None = None,
        summary: str | None = None,
    ) -> AgentAsyncOperation:
        locked_operation = self._lock_operation(db, operation.id)
        if str(locked_operation.status) in TERMINAL_OPERATION_STATUSES:
            return locked_operation
        retrying = retry_at is not None
        status = AgentAsyncOperationStatus.RETRY_SCHEDULED if retrying else AgentAsyncOperationStatus.FAILED
        event_type = "RETRY_SCHEDULED" if retrying else "FAILED"
        locked_operation.status = status
        locked_operation.summary = summary or (
            "客户活动已保存。档案更新暂未完成。系统将自动重试" if retrying else "客户活动已记录。客户档案刷新失败"
        )
        locked_operation.error_message = error_message[:2000]
        locked_operation.next_retry_at = retry_at
        locked_operation.finished_time = None if retrying else business_now()
        self._append_event(
            db,
            locked_operation,
            event_key=f"lifecycle:{event_type.lower()}:{int(locked_operation.attempt_count or 0)}",
            event_type=event_type,
            status=status,
            step=locked_operation.current_step,
            message=locked_operation.summary,
            payload={"next_retry_at": retry_at.isoformat() if retry_at else None},
        )
        db.flush()
        return locked_operation

    def cancel(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        *,
        summary: str,
        result: JSONDict | None = None,
    ) -> AgentAsyncOperation:
        locked_operation = self._lock_operation(db, operation.id)
        if str(locked_operation.status) in TERMINAL_OPERATION_STATUSES:
            return locked_operation
        locked_operation.status = AgentAsyncOperationStatus.CANCELLED
        locked_operation.summary = summary
        locked_operation.result_json = result or {}
        locked_operation.error_message = None
        locked_operation.next_retry_at = None
        locked_operation.finished_time = business_now()
        self._append_event(
            db,
            locked_operation,
            event_key="lifecycle:cancelled",
            event_type="CANCELLED",
            status=AgentAsyncOperationStatus.CANCELLED,
            step=locked_operation.current_step,
            message=summary,
            payload=result,
        )
        db.flush()
        return locked_operation

    def get_by_request_id(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
        user_id: int | None = None,
    ) -> AgentAsyncOperation | None:
        query = db.query(AgentAsyncOperation).filter(
            AgentAsyncOperation.team_id == team_id,
            AgentAsyncOperation.request_id == request_id,
        )
        if user_id is not None:
            query = query.filter(AgentAsyncOperation.user_id == user_id)
        return query.order_by(AgentAsyncOperation.id.desc()).first()

    def get_for_update(
        self,
        db: Session,
        *,
        team_id: int,
        request_id: str,
        operation_public_id: str | None = None,
    ) -> AgentAsyncOperation | None:
        query = db.query(AgentAsyncOperation).filter(AgentAsyncOperation.team_id == team_id)
        if operation_public_id:
            query = query.filter(
                AgentAsyncOperation.public_id == operation_public_id,
                AgentAsyncOperation.request_id == request_id,
            )
        else:
            query = query.filter(AgentAsyncOperation.request_id == request_id)
        return query.order_by(AgentAsyncOperation.id.desc()).populate_existing().with_for_update().first()

    def get_projection(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        public_id: str,
    ) -> AgentAsyncOperationProjection | None:
        operation = (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == team_id,
                AgentAsyncOperation.user_id == user_id,
                AgentAsyncOperation.public_id == public_id,
            )
            .one_or_none()
        )
        return self._projection(operation) if operation is not None else None

    def list_session_projections(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        limit: int = 50,
    ) -> list[AgentAsyncOperationProjection]:
        operations = (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == team_id,
                AgentAsyncOperation.user_id == user_id,
                AgentAsyncOperation.session_id == session_id,
            )
            .order_by(AgentAsyncOperation.created_time.desc(), AgentAsyncOperation.id.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        operations.reverse()
        return [self._projection(operation) for operation in operations]

    def _ensure_scheduled_mysql(
        self,
        db: Session,
        *,
        team_id: int,
        operation_key: str,
        values: JSONDict,
    ) -> AgentAsyncOperation:
        statement = mysql_insert(AgentAsyncOperation).values(**values)
        statement = statement.on_duplicate_key_update(id=func.last_insert_id(AgentAsyncOperation.id))
        result = db.execute(statement)
        operation_id = int(result.lastrowid or 0)
        operation = db.get(AgentAsyncOperation, operation_id) if operation_id > 0 else None
        if (
            operation is None
            or int(operation.team_id) != team_id
            or str(operation.operation_key) != operation_key
        ):
            raise RuntimeError("异步操作幂等键已被其他团队占用")
        return operation

    def _append_event(
        self,
        db: Session,
        operation: AgentAsyncOperation,
        *,
        event_key: str,
        event_type: str,
        status: str,
        step: str | None = None,
        message: str | None = None,
        payload: JSONDict | None = None,
        occurred_at: datetime | None = None,
    ) -> AgentAsyncOperationEvent | None:
        locked_operation = operation
        duplicate = (
            db.query(AgentAsyncOperationEvent.id)
            .filter(
                AgentAsyncOperationEvent.operation_id == locked_operation.id,
                AgentAsyncOperationEvent.event_key == event_key,
            )
            .first()
        )
        if duplicate is not None:
            return None
        sequence = int(locked_operation.next_event_sequence or 1)
        locked_operation.next_event_sequence = sequence + 1
        event = AgentAsyncOperationEvent(
            operation_id=locked_operation.id,
            event_key=event_key,
            sequence=sequence,
            event_type=event_type,
            status=status,
            step=step,
            message=message,
            payload_json=payload or {},
            occurred_at=occurred_at or business_now(),
        )
        db.add(event)
        db.flush()
        return event

    @staticmethod
    def _validate_binding_identity(
        operation: AgentAsyncOperation,
        *,
        operation_key: str,
        request_id: str,
        team_id: int,
        operation_type: str,
        resource_type: str,
        resource_id: int,
    ) -> None:
        expected = {
            "operation_key": operation_key,
            "request_id": request_id,
            "team_id": team_id,
            "operation_type": operation_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        for field, value in expected.items():
            if str(getattr(operation, field)) != str(value):
                raise ValueError(f"异步操作身份校验失败: {field}")

    @staticmethod
    def _lock_operation(db: Session, operation_id: int) -> AgentAsyncOperation:
        return (
            db.query(AgentAsyncOperation)
            .filter(AgentAsyncOperation.id == operation_id)
            .populate_existing()
            .with_for_update()
            .one()
        )

    @staticmethod
    def _get_by_key(db: Session, *, team_id: int, operation_key: str) -> AgentAsyncOperation | None:
        return (
            db.query(AgentAsyncOperation)
            .filter(
                AgentAsyncOperation.team_id == team_id,
                AgentAsyncOperation.operation_key == operation_key,
            )
            .one_or_none()
        )

    @staticmethod
    def _projection(operation: AgentAsyncOperation) -> AgentAsyncOperationProjection:
        events = tuple(
            AgentAsyncOperationEventProjection(
                sequence=int(event.sequence),
                event_type=str(event.event_type),
                status=str(event.status),
                event_key=str(event.event_key),
                step=str(event.step) if event.step is not None else None,
                message=str(event.message) if event.message is not None else None,
                payload=coerce_json_dict(event.payload_json),
                occurred_at=event.occurred_at,
            )
            for event in sorted(operation.events, key=lambda item: int(item.sequence))
        )
        return AgentAsyncOperationProjection(
            public_id=str(operation.public_id),
            request_id=str(operation.request_id),
            team_id=int(operation.team_id),
            user_id=int(operation.user_id),
            session_id=int(operation.session_id) if operation.session_id is not None else None,
            source_user_message_id=(
                int(operation.source_user_message_id) if operation.source_user_message_id is not None else None
            ),
            source_assistant_message_id=(
                int(operation.source_assistant_message_id)
                if operation.source_assistant_message_id is not None
                else None
            ),
            operation_type=str(operation.operation_type),
            resource_type=str(operation.resource_type),
            resource_id=int(operation.resource_id) if operation.resource_id is not None else None,
            resource_public_id=(
                str(operation.resource_public_id) if operation.resource_public_id is not None else None
            ),
            status=str(operation.status),
            summary=str(operation.summary) if operation.summary is not None else None,
            current_step=str(operation.current_step) if operation.current_step is not None else None,
            graph_thread_id=str(operation.graph_thread_id) if operation.graph_thread_id is not None else None,
            result=coerce_json_dict(operation.result_json),
            error_message=str(operation.error_message) if operation.error_message is not None else None,
            started_time=operation.started_time,
            finished_time=operation.finished_time,
            next_retry_at=operation.next_retry_at,
            attempt_count=int(operation.attempt_count or 0),
            created_time=operation.created_time,
            updated_time=operation.updated_time,
            events=events,
        )


agent_async_operation_service = AgentAsyncOperationService()
