from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import false, or_
from sqlalchemy.exc import IntegrityError

from app.models.sales_commitment import (
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEvent,
    FollowUpTaskLLMMatcherRun,
    FollowUpTaskLLMMatcherRunStatus,
    FollowUpTaskProjectionRun,
    FollowUpTaskProjectionStatus,
    FollowUpTaskReconciliationEvaluationRun,
    FollowUpTaskReconciliationEvaluationRunStatus,
    FollowUpTaskReconciliationRun,
    FollowUpTaskReconciliationRunStatus,
    FollowUpTaskStatus,
    FollowUpTaskTransitionPolicyDecisionLog,
    SalesCommitment,
    SalesCommitmentStatus,
)
from app.utils.time import (
    DUE_AT_GRANULARITY_DATETIME,
    FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE,
    business_now,
    calculate_follow_up_task_due_window,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy.orm import Query, Session

    from app.schemas.sales_commitment import (
        FollowUpTaskConfirmationCaseInternalCreate,
        FollowUpTaskConfirmationCaseInternalUpdate,
        FollowUpTaskEventInternalCreate,
        FollowUpTaskInternalCreate,
        FollowUpTaskInternalUpdate,
        FollowUpTaskLLMMatcherRunInternalCreate,
        FollowUpTaskProjectionRunInternalCreate,
        FollowUpTaskProjectionRunInternalUpdate,
        FollowUpTaskReconciliationEvaluationRunInternalCreate,
        FollowUpTaskReconciliationRunInternalCreate,
        FollowUpTaskTransitionPolicyDecisionLogInternalCreate,
        SalesCommitmentInternalCreate,
        SalesCommitmentInternalUpdate,
    )

ModelT = TypeVar("ModelT")


def _dump(obj: object, *, exclude_unset: bool = False) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_unset=exclude_unset)
    return dict(obj)


def _normalize_statuses(statuses: Iterable[str] | None) -> list[str] | None:
    if statuses is None:
        return None
    return [status for status in statuses if status]


def _resolve_source_key(data: dict[str, Any]) -> str:
    source_key = data.get("source_key")
    if source_key:
        return str(source_key)

    source_activity_id = data.get("source_activity_id")
    if source_activity_id is not None:
        return f"activity:{source_activity_id}"

    source_public_id = data.get("source_public_id")
    if source_public_id:
        return f"public:{source_public_id}"

    raise ValueError("source_key、source_activity_id、source_public_id 至少需要提供一个")


def _flush_or_commit(db: Session, db_obj: ModelT, *, commit: bool) -> ModelT:
    if commit:
        db.commit()
        db.refresh(db_obj)
    else:
        db.flush()
    return db_obj


def _apply_status_filter(
    query: Query[Any],
    column: object,
    statuses: Iterable[str] | None,
) -> Query[Any]:
    status_values = _normalize_statuses(statuses)
    if status_values is None:
        return query
    if not status_values:
        return query.filter(false())
    return query.filter(column.in_(status_values))


def _sync_task_status_timestamps(db_obj: FollowUpTask, data: dict[str, Any]) -> None:
    if "status" not in data:
        return

    now = business_now()
    if data["status"] == FollowUpTaskStatus.OPEN:
        db_obj.completed_at = None
        db_obj.cancelled_at = None
    elif data["status"] == FollowUpTaskStatus.COMPLETED:
        db_obj.completed_at = data.get("completed_at") or db_obj.completed_at or now
        db_obj.cancelled_at = None
    elif data["status"] == FollowUpTaskStatus.CANCELLED:
        db_obj.cancelled_at = data.get("cancelled_at") or db_obj.cancelled_at or now
        db_obj.completed_at = None


class SalesCommitmentCRUD:
    def get_by_id(self, db: Session, commitment_id: int, team_id: int | None = None) -> SalesCommitment | None:
        query = db.query(SalesCommitment).filter(SalesCommitment.id == commitment_id)
        if team_id is not None:
            query = query.filter(SalesCommitment.team_id == team_id)
        return query.first()

    def get_by_public_id(self, db: Session, public_id: str, team_id: int | None = None) -> SalesCommitment | None:
        query = db.query(SalesCommitment).filter(SalesCommitment.public_id == public_id)
        if team_id is not None:
            query = query.filter(SalesCommitment.team_id == team_id)
        return query.first()

    def list_public_ids_by_ids(self, db: Session, *, team_id: int, commitment_ids: Iterable[int]) -> list[str]:
        ids = list(dict.fromkeys(commitment_ids))
        if not ids:
            return []
        rows = (
            db.query(SalesCommitment.id, SalesCommitment.public_id)
            .filter(SalesCommitment.team_id == team_id, SalesCommitment.id.in_(ids))
            .all()
        )
        public_ids_by_id = {row.id: row.public_id for row in rows}
        return [public_ids_by_id[commitment_id] for commitment_id in ids if commitment_id in public_ids_by_id]

    def get_by_source_hash(
        self,
        db: Session,
        *,
        team_id: int,
        source_type: str,
        source_key: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        commitment_hash: str,
    ) -> SalesCommitment | None:
        resolved_source_key = source_key or _resolve_source_key(
            {
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
            }
        )
        query = db.query(SalesCommitment).filter(
            SalesCommitment.team_id == team_id,
            SalesCommitment.source_type == source_type,
            SalesCommitment.source_key == resolved_source_key,
            SalesCommitment.commitment_hash == commitment_hash,
        )
        return query.first()

    def get_open_by_source(
        self,
        db: Session,
        *,
        team_id: int,
        source_type: str,
        source_key: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
    ) -> list[SalesCommitment]:
        resolved_source_key = source_key or _resolve_source_key(
            {
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
            }
        )
        query = db.query(SalesCommitment).filter(
            SalesCommitment.team_id == team_id,
            SalesCommitment.source_type == source_type,
            SalesCommitment.source_key == resolved_source_key,
            SalesCommitment.status == SalesCommitmentStatus.OPEN,
        )
        return query.order_by(SalesCommitment.due_at.asc(), SalesCommitment.id.asc()).all()

    def list_for_customer(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        statuses: Iterable[str] | None = None,
        owner_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[SalesCommitment], int]:
        query = db.query(SalesCommitment).filter(
            SalesCommitment.team_id == team_id,
            SalesCommitment.customer_id == customer_id,
        )
        query = _apply_status_filter(query, SalesCommitment.status, statuses)
        if owner_id is not None:
            query = query.filter(SalesCommitment.owner_id == owner_id)
        total = query.count()
        rows = (
            query.order_by(SalesCommitment.due_at.asc(), SalesCommitment.created_time.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def create(
        self,
        db: Session,
        obj_in: SalesCommitmentInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> SalesCommitment:
        data = _dump(obj_in)
        data["source_key"] = _resolve_source_key(data)
        db_obj = SalesCommitment(**data)
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def update(
        self,
        db: Session,
        db_obj: SalesCommitment,
        obj_in: SalesCommitmentInternalUpdate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> SalesCommitment:
        for field, value in _dump(obj_in, exclude_unset=True).items():
            setattr(db_obj, field, value)
        return _flush_or_commit(db, db_obj, commit=commit)


class FollowUpTaskCRUD:
    def get_by_id(self, db: Session, task_id: int, team_id: int | None = None) -> FollowUpTask | None:
        query = db.query(FollowUpTask).filter(FollowUpTask.id == task_id)
        if team_id is not None:
            query = query.filter(FollowUpTask.team_id == team_id)
        return query.first()

    def get_by_public_id(self, db: Session, public_id: str, team_id: int | None = None) -> FollowUpTask | None:
        query = db.query(FollowUpTask).filter(FollowUpTask.public_id == public_id)
        if team_id is not None:
            query = query.filter(FollowUpTask.team_id == team_id)
        return query.first()

    def list_public_ids_by_ids(self, db: Session, *, team_id: int, task_ids: Iterable[int]) -> list[str]:
        ids = list(dict.fromkeys(task_ids))
        if not ids:
            return []
        rows = (
            db.query(FollowUpTask.id, FollowUpTask.public_id)
            .filter(FollowUpTask.team_id == team_id, FollowUpTask.id.in_(ids))
            .all()
        )
        public_ids_by_id = {row.id: row.public_id for row in rows}
        return [public_ids_by_id[task_id] for task_id in ids if task_id in public_ids_by_id]

    def get_by_source_hash(
        self,
        db: Session,
        *,
        team_id: int,
        source_type: str,
        source_key: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        task_hash: str,
    ) -> FollowUpTask | None:
        resolved_source_key = source_key or _resolve_source_key(
            {
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
            }
        )
        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.source_type == source_type,
            FollowUpTask.source_key == resolved_source_key,
            FollowUpTask.task_hash == task_hash,
        )
        return query.first()

    def get_open_by_source(
        self,
        db: Session,
        *,
        team_id: int,
        source_type: str,
        source_key: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
    ) -> list[FollowUpTask]:
        resolved_source_key = source_key or _resolve_source_key(
            {
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
            }
        )
        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.source_type == source_type,
            FollowUpTask.source_key == resolved_source_key,
            FollowUpTask.status == FollowUpTaskStatus.OPEN,
        )
        return query.order_by(FollowUpTask.due_at.asc(), FollowUpTask.id.asc()).all()

    def list_for_owner(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str,
        statuses: Iterable[str] | None = None,
        due_at_start: datetime | None = None,
        due_at_end: datetime | None = None,
        due_window: str | None = None,
        due_window_now: datetime | None = None,
        due_window_timezone: str | None = None,
        customer_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FollowUpTask], int]:
        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.owner_id == owner_id,
        )
        query = self._apply_task_filters(
            query,
            statuses=statuses,
            due_at_start=due_at_start,
            due_at_end=due_at_end,
            due_window=due_window,
            due_window_now=due_window_now,
            due_window_timezone=due_window_timezone,
            customer_id=customer_id,
        )
        total = query.count()
        rows = query.order_by(FollowUpTask.due_at.asc(), FollowUpTask.id.asc()).offset(skip).limit(limit).all()
        return rows, total

    def list_for_customer(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        statuses: Iterable[str] | None = None,
        owner_id: str | None = None,
        due_at_start: datetime | None = None,
        due_at_end: datetime | None = None,
        due_window: str | None = None,
        due_window_now: datetime | None = None,
        due_window_timezone: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FollowUpTask], int]:
        query = db.query(FollowUpTask).filter(
            FollowUpTask.team_id == team_id,
            FollowUpTask.customer_id == customer_id,
        )
        if owner_id is not None:
            query = query.filter(FollowUpTask.owner_id == owner_id)
        query = self._apply_task_filters(
            query,
            statuses=statuses,
            due_at_start=due_at_start,
            due_at_end=due_at_end,
            due_window=due_window,
            due_window_now=due_window_now,
            due_window_timezone=due_window_timezone,
        )
        total = query.count()
        rows = query.order_by(FollowUpTask.due_at.asc(), FollowUpTask.id.asc()).offset(skip).limit(limit).all()
        return rows, total

    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTask:
        data = _dump(obj_in)
        data["source_key"] = _resolve_source_key(data)
        db_obj = FollowUpTask(**data)
        _sync_task_status_timestamps(db_obj, data)
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def update(
        self,
        db: Session,
        db_obj: FollowUpTask,
        obj_in: FollowUpTaskInternalUpdate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTask:
        data = _dump(obj_in, exclude_unset=True)
        for field, value in data.items():
            setattr(db_obj, field, value)
        _sync_task_status_timestamps(db_obj, data)
        return _flush_or_commit(db, db_obj, commit=commit)

    def complete(self, db: Session, db_obj: FollowUpTask, *, commit: bool = True) -> FollowUpTask:
        db_obj.status = FollowUpTaskStatus.COMPLETED
        db_obj.completed_at = business_now()
        db_obj.cancelled_at = None
        return _flush_or_commit(db, db_obj, commit=commit)

    def cancel(self, db: Session, db_obj: FollowUpTask, *, commit: bool = True) -> FollowUpTask:
        db_obj.status = FollowUpTaskStatus.CANCELLED
        db_obj.cancelled_at = business_now()
        db_obj.completed_at = None
        return _flush_or_commit(db, db_obj, commit=commit)

    def reopen(self, db: Session, db_obj: FollowUpTask, *, commit: bool = True) -> FollowUpTask:
        db_obj.status = FollowUpTaskStatus.OPEN
        db_obj.completed_at = None
        db_obj.cancelled_at = None
        return _flush_or_commit(db, db_obj, commit=commit)

    def _apply_task_filters(
        self,
        query: Query[Any],
        *,
        statuses: Iterable[str] | None = None,
        due_at_start: datetime | None = None,
        due_at_end: datetime | None = None,
        due_window: str | None = None,
        due_window_now: datetime | None = None,
        due_window_timezone: str | None = None,
        customer_id: int | None = None,
    ) -> Query[Any]:
        if due_window and (due_at_start is not None or due_at_end is not None):
            raise ValueError("due_window 不能和 due_at_start/due_at_end 同时使用")

        query = _apply_status_filter(query, FollowUpTask.status, statuses)
        if due_window is not None:
            due_query_window = calculate_follow_up_task_due_window(
                due_window,
                now=due_window_now,
                timezone_name=due_window_timezone,
            )
            if due_query_window.name == FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE:
                query = query.filter(
                    or_(
                        FollowUpTask.due_at < due_query_window.ends_at,
                        (
                            (FollowUpTask.due_at_granularity == DUE_AT_GRANULARITY_DATETIME)
                            & (FollowUpTask.due_at < due_query_window.anchor_now)
                        ),
                    )
                )
            else:
                if due_query_window.starts_at is not None:
                    query = query.filter(FollowUpTask.due_at >= due_query_window.starts_at)
                if due_query_window.ends_at is not None:
                    query = query.filter(FollowUpTask.due_at < due_query_window.ends_at)
        if due_at_start is not None:
            query = query.filter(FollowUpTask.due_at >= due_at_start)
        if due_at_end is not None:
            query = query.filter(FollowUpTask.due_at < due_at_end)
        if customer_id is not None:
            query = query.filter(FollowUpTask.customer_id == customer_id)
        return query


class FollowUpTaskEventCRUD:
    def get_by_public_id(self, db: Session, public_id: str, team_id: int | None = None) -> FollowUpTaskEvent | None:
        query = db.query(FollowUpTaskEvent).filter(FollowUpTaskEvent.public_id == public_id)
        if team_id is not None:
            query = query.filter(FollowUpTaskEvent.team_id == team_id)
        return query.first()

    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskEventInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskEvent:
        db_obj = FollowUpTaskEvent(**_dump(obj_in))
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def list_by_task(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FollowUpTaskEvent], int]:
        query = db.query(FollowUpTaskEvent).filter(
            FollowUpTaskEvent.team_id == team_id,
            FollowUpTaskEvent.task_id == task_id,
        )
        total = query.count()
        rows = (
            query.order_by(FollowUpTaskEvent.created_time.asc(), FollowUpTaskEvent.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def record_status_change(
        self,
        db: Session,
        *,
        task: FollowUpTask,
        event_type: str,
        actor_id: str | None,
        previous_status: str | None,
        payload_json: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> FollowUpTaskEvent:
        return self.create(
            db,
            {
                "team_id": task.team_id,
                "task_id": task.id,
                "event_type": event_type,
                "actor_id": actor_id,
                "source_type": task.source_type,
                "source_activity_id": task.source_activity_id,
                "source_public_id": task.source_public_id,
                "previous_status": previous_status,
                "new_status": task.status,
                "payload_json": payload_json,
            },
            commit=commit,
        )


class FollowUpTaskProjectionRunCRUD:
    def get_by_id(self, db: Session, run_id: int, team_id: int | None = None) -> FollowUpTaskProjectionRun | None:
        query = db.query(FollowUpTaskProjectionRun).filter(FollowUpTaskProjectionRun.id == run_id)
        if team_id is not None:
            query = query.filter(FollowUpTaskProjectionRun.team_id == team_id)
        return query.first()

    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int | None = None,
    ) -> FollowUpTaskProjectionRun | None:
        query = db.query(FollowUpTaskProjectionRun).filter(FollowUpTaskProjectionRun.public_id == public_id)
        if team_id is not None:
            query = query.filter(FollowUpTaskProjectionRun.team_id == team_id)
        return query.first()

    def create_running(
        self,
        db: Session,
        obj_in: FollowUpTaskProjectionRunInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskProjectionRun:
        data = _dump(obj_in)
        data["status"] = FollowUpTaskProjectionStatus.RUNNING
        data["source_key"] = _resolve_source_key(data)
        db_obj = FollowUpTaskProjectionRun(**data)
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def update(
        self,
        db: Session,
        db_obj: FollowUpTaskProjectionRun,
        obj_in: FollowUpTaskProjectionRunInternalUpdate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskProjectionRun:
        for field, value in _dump(obj_in, exclude_unset=True).items():
            setattr(db_obj, field, value)
        return _flush_or_commit(db, db_obj, commit=commit)

    def mark_success(
        self,
        db: Session,
        db_obj: FollowUpTaskProjectionRun,
        *,
        created_task_ids: list[int] | None = None,
        updated_task_ids: list[int] | None = None,
        cancelled_task_ids: list[int] | None = None,
        created_commitment_ids: list[int] | None = None,
        updated_commitment_ids: list[int] | None = None,
        projection_hash: str | None = None,
        duration_ms: int | None = None,
        commit: bool = True,
    ) -> FollowUpTaskProjectionRun:
        created_task_ids = created_task_ids or []
        updated_task_ids = updated_task_ids or []
        cancelled_task_ids = cancelled_task_ids or []
        created_commitment_ids = created_commitment_ids or []
        updated_commitment_ids = updated_commitment_ids or []
        return self.update(
            db,
            db_obj,
            {
                "status": FollowUpTaskProjectionStatus.SUCCESS,
                "projection_hash": projection_hash,
                "task_count": len(set(created_task_ids + updated_task_ids + cancelled_task_ids)),
                "commitment_count": len(set(created_commitment_ids + updated_commitment_ids)),
                "created_task_ids_json": created_task_ids,
                "updated_task_ids_json": updated_task_ids,
                "cancelled_task_ids_json": cancelled_task_ids,
                "created_commitment_ids_json": created_commitment_ids,
                "updated_commitment_ids_json": updated_commitment_ids,
                "duration_ms": duration_ms,
                "finished_at": business_now(),
            },
            commit=commit,
        )

    def mark_skipped(
        self,
        db: Session,
        db_obj: FollowUpTaskProjectionRun,
        *,
        skip_reason: str,
        created_task_ids: list[int] | None = None,
        updated_task_ids: list[int] | None = None,
        cancelled_task_ids: list[int] | None = None,
        created_commitment_ids: list[int] | None = None,
        updated_commitment_ids: list[int] | None = None,
        projection_hash: str | None = None,
        duration_ms: int | None = None,
        commit: bool = True,
    ) -> FollowUpTaskProjectionRun:
        created_task_ids = created_task_ids or []
        updated_task_ids = updated_task_ids or []
        cancelled_task_ids = cancelled_task_ids or []
        created_commitment_ids = created_commitment_ids or []
        updated_commitment_ids = updated_commitment_ids or []
        return self.update(
            db,
            db_obj,
            {
                "status": FollowUpTaskProjectionStatus.SKIPPED,
                "skip_reason": skip_reason,
                "projection_hash": projection_hash,
                "task_count": len(set(created_task_ids + updated_task_ids + cancelled_task_ids)),
                "commitment_count": len(set(created_commitment_ids + updated_commitment_ids)),
                "created_task_ids_json": created_task_ids,
                "updated_task_ids_json": updated_task_ids,
                "cancelled_task_ids_json": cancelled_task_ids,
                "created_commitment_ids_json": created_commitment_ids,
                "updated_commitment_ids_json": updated_commitment_ids,
                "duration_ms": duration_ms,
                "finished_at": business_now(),
            },
            commit=commit,
        )

    def mark_failed(
        self,
        db: Session,
        db_obj: FollowUpTaskProjectionRun,
        *,
        error_message: str,
        duration_ms: int | None = None,
        commit: bool = True,
    ) -> FollowUpTaskProjectionRun:
        return self.update(
            db,
            db_obj,
            {
                "status": FollowUpTaskProjectionStatus.FAILED,
                "error_message": error_message[:4000],
                "duration_ms": duration_ms,
                "finished_at": business_now(),
            },
            commit=commit,
        )

    def list_by_source(
        self,
        db: Session,
        *,
        team_id: int,
        source_type: str,
        source_key: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FollowUpTaskProjectionRun], int]:
        resolved_source_key = source_key or _resolve_source_key(
            {
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
            }
        )
        query = db.query(FollowUpTaskProjectionRun).filter(
            FollowUpTaskProjectionRun.team_id == team_id,
            FollowUpTaskProjectionRun.source_type == source_type,
            FollowUpTaskProjectionRun.source_key == resolved_source_key,
        )
        total = query.count()
        rows = (
            query.order_by(FollowUpTaskProjectionRun.created_time.desc(), FollowUpTaskProjectionRun.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def list_failed(
        self,
        db: Session,
        *,
        team_id: int,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FollowUpTaskProjectionRun], int]:
        query = db.query(FollowUpTaskProjectionRun).filter(
            FollowUpTaskProjectionRun.team_id == team_id,
            FollowUpTaskProjectionRun.status == FollowUpTaskProjectionStatus.FAILED,
        )
        if source_type is not None:
            query = query.filter(FollowUpTaskProjectionRun.source_type == source_type)
        total = query.count()
        rows = (
            query.order_by(FollowUpTaskProjectionRun.created_time.asc(), FollowUpTaskProjectionRun.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def list_by_source_activity(
        self,
        db: Session,
        *,
        team_id: int,
        source_type: str,
        source_activity_id: int | None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FollowUpTaskProjectionRun], int]:
        return self.list_by_source(
            db,
            team_id=team_id,
            source_type=source_type,
            source_activity_id=source_activity_id,
            skip=skip,
            limit=limit,
        )


class FollowUpTaskConfirmationCaseCRUD:
    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int | None = None,
    ) -> FollowUpTaskConfirmationCase | None:
        query = db.query(FollowUpTaskConfirmationCase).filter(FollowUpTaskConfirmationCase.public_id == public_id)
        if team_id is not None:
            query = query.filter(FollowUpTaskConfirmationCase.team_id == team_id)
        return query.first()

    def get_pending_by_hash(
        self,
        db: Session,
        *,
        team_id: int,
        confirmation_hash: str,
    ) -> FollowUpTaskConfirmationCase | None:
        return (
            db.query(FollowUpTaskConfirmationCase)
            .filter(
                FollowUpTaskConfirmationCase.team_id == team_id,
                FollowUpTaskConfirmationCase.confirmation_hash == confirmation_hash,
                FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
            )
            .first()
        )

    def list_pending_for_owner(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str,
        skip: int = 0,
        limit: int = 100,
        now: datetime | None = None,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]:
        resolved_now = now or business_now()
        query = db.query(FollowUpTaskConfirmationCase).filter(
            FollowUpTaskConfirmationCase.team_id == team_id,
            FollowUpTaskConfirmationCase.owner_id == owner_id,
            FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
            or_(
                FollowUpTaskConfirmationCase.expires_at.is_(None),
                FollowUpTaskConfirmationCase.expires_at > resolved_now,
            ),
        )
        total = query.count()
        rows = (
            query.order_by(FollowUpTaskConfirmationCase.created_time.asc(), FollowUpTaskConfirmationCase.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def list_expired_pending(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        before: datetime | None = None,
        skip: int = 0,
        limit: int = 500,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]:
        resolved_before = before or business_now()
        query = db.query(FollowUpTaskConfirmationCase).filter(
            FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
            FollowUpTaskConfirmationCase.expires_at.is_not(None),
            FollowUpTaskConfirmationCase.expires_at <= resolved_before,
        )
        if team_id is not None:
            query = query.filter(FollowUpTaskConfirmationCase.team_id == team_id)
        total = query.count()
        rows = (
            query.order_by(FollowUpTaskConfirmationCase.expires_at.asc(), FollowUpTaskConfirmationCase.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def list_pending_by_task(
        self,
        db: Session,
        *,
        team_id: int,
        task_id: int,
        skip: int = 0,
        limit: int = 500,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]:
        query = db.query(FollowUpTaskConfirmationCase).filter(
            FollowUpTaskConfirmationCase.team_id == team_id,
            FollowUpTaskConfirmationCase.task_id == task_id,
            FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
        )
        total = query.count()
        rows = (
            query.order_by(FollowUpTaskConfirmationCase.created_time.asc(), FollowUpTaskConfirmationCase.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def list_pending_by_source_activity(
        self,
        db: Session,
        *,
        team_id: int,
        source_activity_id: int,
        skip: int = 0,
        limit: int = 500,
    ) -> tuple[list[FollowUpTaskConfirmationCase], int]:
        query = db.query(FollowUpTaskConfirmationCase).filter(
            FollowUpTaskConfirmationCase.team_id == team_id,
            FollowUpTaskConfirmationCase.source_activity_id == source_activity_id,
            FollowUpTaskConfirmationCase.status == FollowUpTaskConfirmationStatus.PENDING,
        )
        total = query.count()
        rows = (
            query.order_by(FollowUpTaskConfirmationCase.created_time.asc(), FollowUpTaskConfirmationCase.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return rows, total

    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskConfirmationCaseInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        db_obj = FollowUpTaskConfirmationCase(**_dump(obj_in))
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def update(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        obj_in: FollowUpTaskConfirmationCaseInternalUpdate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        for field, value in _dump(obj_in, exclude_unset=True).items():
            setattr(db_obj, field, value)
        return _flush_or_commit(db, db_obj, commit=commit)

    def mark_prompted(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        prompted_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        return self.update(
            db,
            db_obj,
            {
                "last_prompted_at": prompted_at or business_now(),
                "prompt_count": int(db_obj.prompt_count or 0) + 1,
            },
            commit=commit,
        )

    def record_unresolved_reply(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        reply_text: str,
        actor_id: str,
        replied_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        return self.update(
            db,
            db_obj,
            {
                "unresolved_reply_count": int(db_obj.unresolved_reply_count or 0) + 1,
                "last_unresolved_reply_text": reply_text,
                "last_unresolved_reply_by_id": actor_id,
                "last_unresolved_reply_at": replied_at or business_now(),
            },
            commit=commit,
        )

    def resolve(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        resolved_action: str,
        resolved_by_id: str,
        resolution_text: str,
        resolved_due_at: datetime | None = None,
        resolved_due_at_text: str | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        return self.update(
            db,
            db_obj,
            {
                "status": FollowUpTaskConfirmationStatus.RESOLVED,
                "resolved_action": resolved_action,
                "resolved_due_at": resolved_due_at,
                "resolved_due_at_text": resolved_due_at_text,
                "resolution_text": resolution_text,
                "resolved_by_id": resolved_by_id,
                "resolved_at": business_now(),
            },
            commit=commit,
        )

    def mark_expired(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        expired_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        return self.update(
            db,
            db_obj,
            {
                "status": FollowUpTaskConfirmationStatus.EXPIRED,
                "expired_at": expired_at or business_now(),
            },
            commit=commit,
        )

    def mark_cancelled(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        cancelled_at: datetime | None = None,
        cancelled_by_id: str | None = None,
        cancelled_reason: str,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        return self.update(
            db,
            db_obj,
            {
                "status": FollowUpTaskConfirmationStatus.CANCELLED,
                "cancelled_at": cancelled_at or business_now(),
                "cancelled_by_id": cancelled_by_id,
                "cancelled_reason": cancelled_reason,
            },
            commit=commit,
        )

    def mark_application_result(
        self,
        db: Session,
        db_obj: FollowUpTaskConfirmationCase,
        *,
        application_status: str,
        applied_by_id: str,
        application_skip_reason: str | None = None,
        application_result_json: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCase:
        return self.update(
            db,
            db_obj,
            {
                "application_status": application_status,
                "application_skip_reason": application_skip_reason,
                "application_result_json": application_result_json,
                "applied_by_id": applied_by_id,
                "applied_at": business_now(),
            },
            commit=commit,
        )


class FollowUpTaskConfirmationPromptDeliveryCRUD:
    def get_by_prompt_key(
        self,
        db: Session,
        *,
        team_id: int,
        prompt_key: str,
    ) -> FollowUpTaskConfirmationPromptDelivery | None:
        return (
            db.query(FollowUpTaskConfirmationPromptDelivery)
            .filter(
                FollowUpTaskConfirmationPromptDelivery.team_id == team_id,
                FollowUpTaskConfirmationPromptDelivery.prompt_key == prompt_key,
            )
            .order_by(FollowUpTaskConfirmationPromptDelivery.id.desc())
            .first()
        )

    def create_attempt(
        self,
        db: Session,
        *,
        team_id: int,
        case_id: int,
        owner_id: str,
        channel: str,
        interaction_id: str,
        prompt_key: str,
        status: str,
        reason_code: str | None = None,
        provider: str | None = None,
        agent_session_id: int | None = None,
        payload_json: dict[str, Any] | None = None,
        error_message: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        attempted_at: datetime | None = None,
        delivered_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationPromptDelivery:
        existing = self.get_by_prompt_key(db, team_id=team_id, prompt_key=prompt_key)
        if existing is not None:
            return existing
        resolved_attempted_at = attempted_at or business_now()
        db_obj = FollowUpTaskConfirmationPromptDelivery(
            team_id=team_id,
            case_id=case_id,
            owner_id=owner_id,
            channel=channel,
            provider=provider,
            agent_session_id=agent_session_id,
            interaction_id=interaction_id,
            prompt_key=prompt_key,
            status=status,
            payload_json=payload_json,
            reason_code=reason_code,
            error_message=error_message,
            thread_id=thread_id,
            run_id=run_id,
            attempted_at=resolved_attempted_at,
            delivered_at=delivered_at,
            prompted_at=resolved_attempted_at,
        )
        try:
            with db.begin_nested():
                db.add(db_obj)
                db.flush()
        except IntegrityError:
            existing = self.get_by_prompt_key(db, team_id=team_id, prompt_key=prompt_key)
            if existing is None:
                raise
            return existing

        if commit:
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def update_attempt_status(
        self,
        db: Session,
        delivery: FollowUpTaskConfirmationPromptDelivery,
        *,
        status: str,
        reason_code: str | None = None,
        error_message: str | None = None,
        attempted_at: datetime | None = None,
        delivered_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationPromptDelivery:
        delivery.status = status
        delivery.reason_code = reason_code
        delivery.error_message = error_message
        if attempted_at is not None:
            delivery.attempted_at = attempted_at
        delivery.delivered_at = delivered_at
        db.add(delivery)
        if commit:
            db.commit()
            db.refresh(delivery)
        return delivery

    def latest_for_owner_since(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str,
        since: datetime,
    ) -> FollowUpTaskConfirmationPromptDelivery | None:
        return (
            db.query(FollowUpTaskConfirmationPromptDelivery)
            .filter(
                FollowUpTaskConfirmationPromptDelivery.team_id == team_id,
                FollowUpTaskConfirmationPromptDelivery.owner_id == owner_id,
                FollowUpTaskConfirmationPromptDelivery.status == FollowUpTaskConfirmationPromptStatus.SENT,
                FollowUpTaskConfirmationPromptDelivery.prompted_at >= since,
            )
            .order_by(
                FollowUpTaskConfirmationPromptDelivery.prompted_at.desc(),
                FollowUpTaskConfirmationPromptDelivery.id.desc(),
            )
            .first()
        )

    def latest_for_case_since(
        self,
        db: Session,
        *,
        team_id: int,
        case_id: int,
        since: datetime,
    ) -> FollowUpTaskConfirmationPromptDelivery | None:
        return (
            db.query(FollowUpTaskConfirmationPromptDelivery)
            .filter(
                FollowUpTaskConfirmationPromptDelivery.team_id == team_id,
                FollowUpTaskConfirmationPromptDelivery.case_id == case_id,
                FollowUpTaskConfirmationPromptDelivery.status == FollowUpTaskConfirmationPromptStatus.SENT,
                FollowUpTaskConfirmationPromptDelivery.prompted_at >= since,
            )
            .order_by(
                FollowUpTaskConfirmationPromptDelivery.prompted_at.desc(),
                FollowUpTaskConfirmationPromptDelivery.id.desc(),
            )
            .first()
        )

    def create_sent(
        self,
        db: Session,
        *,
        team_id: int,
        case_id: int,
        owner_id: str,
        channel: str,
        provider: str | None,
        agent_session_id: int | None,
        interaction_id: str,
        prompt_key: str,
        payload_json: dict[str, Any] | None = None,
        prompted_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationPromptDelivery:
        resolved_prompted_at = prompted_at or business_now()
        return self.create_attempt(
            db,
            team_id=team_id,
            case_id=case_id,
            owner_id=owner_id,
            channel=channel,
            provider=provider,
            agent_session_id=agent_session_id,
            interaction_id=interaction_id,
            prompt_key=prompt_key,
            status=FollowUpTaskConfirmationPromptStatus.SENT,
            reason_code="CHANNEL_DISPATCHED",
            payload_json=payload_json,
            attempted_at=resolved_prompted_at,
            delivered_at=resolved_prompted_at,
            commit=commit,
        )


class FollowUpTaskTransitionPolicyDecisionLogCRUD:
    def record_result(
        self,
        db: Session,
        *,
        policy_result: Any,
        owner_id: str | None,
        actor_id: str | None = None,
        task: FollowUpTask | None = None,
        source_type: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        context_json: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> FollowUpTaskTransitionPolicyDecisionLog:
        policy_snapshot = policy_result.to_dict() if hasattr(policy_result, "to_dict") else dict(policy_result)
        resolved_source_type = source_type or (task.source_type if task is not None else None)
        resolved_source_activity_id = source_activity_id
        if resolved_source_activity_id is None and task is not None:
            resolved_source_activity_id = task.source_activity_id
        resolved_source_public_id = source_public_id
        if resolved_source_public_id is None and task is not None:
            resolved_source_public_id = task.source_public_id
        return self.create(
            db,
            {
                "team_id": policy_snapshot["team_id"],
                "owner_id": owner_id,
                "actor_id": actor_id,
                "task_id": task.id if task is not None else None,
                "source_type": resolved_source_type,
                "source_activity_id": resolved_source_activity_id,
                "source_public_id": resolved_source_public_id,
                "action": policy_snapshot.get("action"),
                "allowed": bool(policy_snapshot["allowed"]),
                "reason": policy_snapshot["reason"],
                "enabled": bool(policy_snapshot["enabled"]),
                "owner_allowlist_configured": bool(policy_snapshot.get("owner_allowlist_configured", False)),
                "allowed_actions_json": list(policy_snapshot.get("allowed_actions") or []),
                "config_errors_json": list(policy_snapshot.get("config_errors") or []),
                "policy_result_json": policy_snapshot,
                "context_json": context_json,
            },
            commit=commit,
        )

    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskTransitionPolicyDecisionLogInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskTransitionPolicyDecisionLog:
        db_obj = FollowUpTaskTransitionPolicyDecisionLog(**_dump(obj_in))
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)


class FollowUpTaskReconciliationRunCRUD:
    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskReconciliationRunInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskReconciliationRun:
        data = _dump(obj_in)
        data["finished_at"] = data.get("finished_at") or business_now()
        data["started_at"] = data.get("started_at") or data["finished_at"]
        db_obj = FollowUpTaskReconciliationRun(**data)
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def record_success(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int | None,
        owner_id: str | None,
        actor_id: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        include_cross_owner: bool,
        lookback_days: int,
        lookahead_days: int,
        limit: int,
        candidate_public_ids: list[str],
        filters_json: dict[str, Any],
        usage_policy_json: dict[str, Any],
        anchor_at: datetime | None,
        duration_ms: int | None,
        started_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskReconciliationRun:
        candidate_count = len(candidate_public_ids)
        status = (
            FollowUpTaskReconciliationRunStatus.SUCCESS
            if candidate_count > 0
            else FollowUpTaskReconciliationRunStatus.SKIPPED
        )
        return self.create(
            db,
            {
                "team_id": team_id,
                "customer_id": customer_id,
                "owner_id": owner_id,
                "actor_id": actor_id,
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
                "status": status,
                "skip_reason": None if candidate_count > 0 else "NO_OPEN_CANDIDATES",
                "include_cross_owner": include_cross_owner,
                "lookback_days": lookback_days,
                "lookahead_days": lookahead_days,
                "limit": limit,
                "candidate_count": candidate_count,
                "candidate_public_ids_json": candidate_public_ids,
                "filters_json": filters_json,
                "usage_policy_json": usage_policy_json,
                "duration_ms": duration_ms,
                "anchor_at": anchor_at,
                "started_at": started_at,
                "finished_at": business_now(),
            },
            commit=commit,
        )

    def record_failed(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int | None = None,
        owner_id: str | None = None,
        actor_id: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        include_cross_owner: bool = False,
        lookback_days: int = 90,
        lookahead_days: int = 30,
        limit: int = 20,
        error_message: str,
        anchor_at: datetime | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskReconciliationRun:
        return self.create(
            db,
            {
                "team_id": team_id,
                "customer_id": customer_id,
                "owner_id": owner_id,
                "actor_id": actor_id,
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
                "status": FollowUpTaskReconciliationRunStatus.FAILED,
                "skip_reason": "ERROR",
                "include_cross_owner": include_cross_owner,
                "lookback_days": lookback_days,
                "lookahead_days": lookahead_days,
                "limit": limit,
                "candidate_count": 0,
                "candidate_public_ids_json": [],
                "filters_json": None,
                "usage_policy_json": None,
                "error_message": error_message[:4000],
                "duration_ms": duration_ms,
                "anchor_at": anchor_at,
                "started_at": started_at,
                "finished_at": business_now(),
            },
            commit=commit,
        )


class FollowUpTaskLLMMatcherRunCRUD:
    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskLLMMatcherRunInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskLLMMatcherRun:
        data = _dump(obj_in)
        data["finished_at"] = data.get("finished_at") or business_now()
        data["started_at"] = data.get("started_at") or data["finished_at"]
        db_obj = FollowUpTaskLLMMatcherRun(**data)
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def record_match_result(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str | None,
        result: Any,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        actor_id: str | None = None,
        reconciliation_run_public_id: str | None = None,
        model_name: str | None = None,
        structured_output_strategy: str | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskLLMMatcherRun:
        decision = result.decision
        resolved_status = status or (
            FollowUpTaskLLMMatcherRunStatus.SUCCESS
            if result.source != "safe_fallback" or not decision.forbid_auto_reasons
            else FollowUpTaskLLMMatcherRunStatus.SKIPPED
        )
        return self.create(
            db,
            {
                "team_id": team_id,
                "owner_id": owner_id,
                "actor_id": actor_id,
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
                "reconciliation_run_public_id": reconciliation_run_public_id,
                "status": resolved_status,
                "source": result.source,
                "decision": decision.decision,
                "task_public_id": decision.task_public_id,
                "candidate_public_ids_json": list(decision.candidate_public_ids),
                "confidence": decision.confidence,
                "needs_confirmation": decision.needs_confirmation,
                "forbid_auto_reasons_json": list(decision.forbid_auto_reasons),
                "evidence_terms_json": list(decision.evidence_terms),
                "referenced_source_public_ids_json": list(result.referenced_source_public_ids),
                "evaluation_failures_json": list(result.evaluation_failures),
                "model_name": model_name,
                "structured_output_strategy": structured_output_strategy,
                "duration_ms": duration_ms,
                "started_at": started_at,
                "finished_at": business_now(),
            },
            commit=commit,
        )

    def record_schema_error(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str | None,
        candidate_public_ids: list[str],
        error: Exception,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        actor_id: str | None = None,
        reconciliation_run_public_id: str | None = None,
        model_name: str | None = None,
        structured_output_strategy: str | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskLLMMatcherRun:
        return self.create(
            db,
            {
                "team_id": team_id,
                "owner_id": owner_id,
                "actor_id": actor_id,
                "source_activity_id": source_activity_id,
                "source_public_id": source_public_id,
                "reconciliation_run_public_id": reconciliation_run_public_id,
                "status": FollowUpTaskLLMMatcherRunStatus.FAILED,
                "source": "structured_output_error",
                "decision": "KEEP_OPEN",
                "candidate_public_ids_json": candidate_public_ids,
                "confidence": 0.0,
                "needs_confirmation": False,
                "forbid_auto_reasons_json": ["STRUCTURED_OUTPUT_FAILED"],
                "evaluation_failures_json": [],
                "model_name": model_name,
                "structured_output_strategy": structured_output_strategy,
                "schema_error_type": type(error).__name__,
                "schema_error_message": str(error)[:4000],
                "duration_ms": duration_ms,
                "started_at": started_at,
                "finished_at": business_now(),
            },
            commit=commit,
        )


class FollowUpTaskReconciliationEvaluationRunCRUD:
    def create(
        self,
        db: Session,
        obj_in: FollowUpTaskReconciliationEvaluationRunInternalCreate | dict[str, Any],
        *,
        commit: bool = True,
    ) -> FollowUpTaskReconciliationEvaluationRun:
        data = _dump(obj_in)
        data["finished_at"] = data.get("finished_at") or business_now()
        data["started_at"] = data.get("started_at") or data["finished_at"]
        db_obj = FollowUpTaskReconciliationEvaluationRun(**data)
        db.add(db_obj)
        return _flush_or_commit(db, db_obj, commit=commit)

    def record_summary(
        self,
        db: Session,
        *,
        suite_name: str,
        summary: Any,
        team_id: int | None = None,
        fixture_path: str | None = None,
        fixture_hash: str | None = None,
        thresholds_json: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskReconciliationEvaluationRun:
        metrics_snapshot = summary.metrics.to_dict() if hasattr(summary.metrics, "to_dict") else dict(summary.metrics)
        false_close_metric = _metric_snapshot(metrics_snapshot, "false_close")
        false_delay_metric = _metric_snapshot(metrics_snapshot, "false_delay")
        missed_confirmation_metric = _metric_snapshot(metrics_snapshot, "missed_confirmation")
        over_confirmation_metric = _metric_snapshot(metrics_snapshot, "over_confirmation")
        failure_cases = [
            {
                "case_name": result.case_name,
                "failures": list(result.failures),
            }
            for result in summary.results
            if not result.passed
        ]
        case_results = [
            {
                "case_name": result.case_name,
                "passed": result.passed,
                "failures": list(result.failures),
            }
            for result in summary.results
        ]
        return self.create(
            db,
            {
                "team_id": team_id,
                "suite_name": suite_name,
                "fixture_path": fixture_path,
                "fixture_hash": fixture_hash,
                "status": FollowUpTaskReconciliationEvaluationRunStatus.SUCCESS,
                "ok": bool(summary.ok),
                "total_cases": summary.total,
                "passed_cases": summary.passed,
                "failed_cases": summary.failed,
                "false_close_count": false_close_metric["count"],
                "false_close_rate": false_close_metric["rate"],
                "false_delay_count": false_delay_metric["count"],
                "false_delay_rate": false_delay_metric["rate"],
                "missed_confirmation_count": missed_confirmation_metric["count"],
                "missed_confirmation_rate": missed_confirmation_metric["rate"],
                "over_confirmation_count": over_confirmation_metric["count"],
                "over_confirmation_rate": over_confirmation_metric["rate"],
                "metrics_json": metrics_snapshot,
                "failure_cases_json": failure_cases,
                "case_results_json": case_results,
                "thresholds_json": thresholds_json,
                "duration_ms": duration_ms,
                "started_at": started_at,
                "finished_at": business_now(),
            },
            commit=commit,
        )

    def record_failed(
        self,
        db: Session,
        *,
        suite_name: str,
        error_message: str,
        team_id: int | None = None,
        fixture_path: str | None = None,
        fixture_hash: str | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        commit: bool = True,
    ) -> FollowUpTaskReconciliationEvaluationRun:
        return self.create(
            db,
            {
                "team_id": team_id,
                "suite_name": suite_name,
                "fixture_path": fixture_path,
                "fixture_hash": fixture_hash,
                "status": FollowUpTaskReconciliationEvaluationRunStatus.FAILED,
                "ok": False,
                "error_message": error_message[:4000],
                "duration_ms": duration_ms,
                "started_at": started_at,
                "finished_at": business_now(),
            },
            commit=commit,
        )


def _metric_snapshot(metrics_snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    metric = metrics_snapshot.get(name)
    if not isinstance(metric, dict):
        return {"count": 0, "rate": 0.0}
    count = metric.get("count", 0)
    rate = metric.get("rate", 0.0)
    return {
        "count": count if isinstance(count, int) else 0,
        "rate": rate if isinstance(rate, int | float) else 0.0,
    }


sales_commitment_crud = SalesCommitmentCRUD()
follow_up_task_crud = FollowUpTaskCRUD()
follow_up_task_event_crud = FollowUpTaskEventCRUD()
follow_up_task_projection_run_crud = FollowUpTaskProjectionRunCRUD()
follow_up_task_confirmation_case_crud = FollowUpTaskConfirmationCaseCRUD()
follow_up_task_confirmation_prompt_delivery_crud = FollowUpTaskConfirmationPromptDeliveryCRUD()
follow_up_task_transition_policy_decision_log_crud = FollowUpTaskTransitionPolicyDecisionLogCRUD()
follow_up_task_reconciliation_run_crud = FollowUpTaskReconciliationRunCRUD()
follow_up_task_llm_matcher_run_crud = FollowUpTaskLLMMatcherRunCRUD()
follow_up_task_reconciliation_evaluation_run_crud = FollowUpTaskReconciliationEvaluationRunCRUD()
