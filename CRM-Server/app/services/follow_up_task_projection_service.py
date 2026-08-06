from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.crud.customer_activity import customer_activity_crud
from app.crud.sales_commitment import (
    follow_up_task_crud,
    follow_up_task_event_crud,
    follow_up_task_projection_run_crud,
    sales_commitment_crud,
)
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskEventType,
    FollowUpTaskProjectionStatus,
    FollowUpTaskProjectionTrigger,
    FollowUpTaskSourceType,
    SalesCommitment,
    SalesCommitmentStatus,
)
from app.schemas.sales_commitment import (
    FollowUpTaskInternalCreate,
    FollowUpTaskProjectionRunInternalCreate,
    SalesCommitmentInternalCreate,
)
from app.services.customer_vector_document_service import customer_vector_document_service
from app.services.follow_up_task_confirmation_cleanup_service import (
    FollowUpTaskConfirmationCancelReason,
    follow_up_task_confirmation_cleanup_service,
)
from app.utils.time import normalize_due_at

logger = logging.getLogger(__name__)


class FollowUpTaskProjectionSkipReason:
    ACTIVITY_NOT_FOUND = "ACTIVITY_NOT_FOUND"
    NO_NEXT_STEP = "NO_NEXT_STEP"
    NO_DUE_AT = "NO_DUE_AT"
    NO_CHANGE = "NO_CHANGE"
    SOURCE_NEXT_STEP_REMOVED = "SOURCE_NEXT_STEP_REMOVED"
    SOURCE_ACTIVITY_DELETED = "SOURCE_ACTIVITY_DELETED"
    SUPERSEDED_INPUT = "SUPERSEDED_INPUT"


@dataclass(frozen=True)
class FollowUpTaskProjectionResult:
    trigger_type: str
    source_type: str
    source_key: str | None
    input_snapshot_hash: str | None
    projection_hash: str | None
    skip_reason: str | None = None
    created_task_ids: list[int] = field(default_factory=list)
    updated_task_ids: list[int] = field(default_factory=list)
    cancelled_task_ids: list[int] = field(default_factory=list)
    created_commitment_ids: list[int] = field(default_factory=list)
    updated_commitment_ids: list[int] = field(default_factory=list)
    projection_run_id: int | None = None
    projection_run_status: str | None = None
    error_message: str | None = None

    @property
    def task_count(self) -> int:
        return len(set(self.created_task_ids + self.updated_task_ids + self.cancelled_task_ids))

    @property
    def commitment_count(self) -> int:
        return len(set(self.created_commitment_ids + self.updated_commitment_ids))


class FollowUpTaskProjectionService:
    def run_activity_projection(
        self,
        db: Session,
        *,
        activity_id: int,
        trigger_type: str,
        actor_id: str | None = None,
        activity_snapshot: CustomerActivity | None = None,
        team_id: int | None = None,
        attempt_count: int = 1,
        commit: bool = True,
    ) -> FollowUpTaskProjectionResult:
        self._validate_trigger_type(trigger_type)
        activity = activity_snapshot or customer_activity_crud.get_by_id(db, activity_id)
        if activity is None:
            if team_id is None:
                raise ValueError("活动不存在时必须提供 team_id 才能记录投影运行")
            return self._record_missing_activity_run(
                db,
                activity_id=activity_id,
                trigger_type=trigger_type,
                actor_id=actor_id,
                team_id=team_id,
                attempt_count=attempt_count,
                commit=commit,
            )

        source_key = _activity_source_key(activity)
        input_snapshot_hash = _stable_hash(_activity_snapshot(activity))
        run = follow_up_task_projection_run_crud.create_running(
            db,
            FollowUpTaskProjectionRunInternalCreate(
                team_id=activity.team_id,
                trigger_type=trigger_type,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=source_key,
                source_activity_id=activity.id,
                actor_id=actor_id,
                input_snapshot_hash=input_snapshot_hash,
                attempt_count=attempt_count,
            ),
            commit=False,
        )
        started_monotonic = time.perf_counter()

        try:
            with db.begin_nested():
                result = self.project_activity(
                    db,
                    activity_id=activity_id,
                    trigger_type=trigger_type,
                    actor_id=actor_id,
                    activity_snapshot=activity,
                    commit=False,
                )
        except Exception as exc:  # pragma: no cover - exercised through tests with monkeypatch
            duration_ms = _elapsed_ms(started_monotonic)
            failed_run = follow_up_task_projection_run_crud.mark_failed(
                db,
                run,
                error_message=str(exc),
                duration_ms=duration_ms,
                commit=False,
            )
            if commit:
                db.commit()
                db.refresh(failed_run)
            _log_projection_run_result(
                db,
                activity_id=activity_id,
                trigger_type=trigger_type,
                run=failed_run,
                status=FollowUpTaskProjectionStatus.FAILED,
                skip_reason=None,
                task_ids=[],
                error_message=failed_run.error_message,
            )
            return FollowUpTaskProjectionResult(
                trigger_type=trigger_type,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=source_key,
                input_snapshot_hash=input_snapshot_hash,
                projection_hash=None,
                projection_run_id=failed_run.id,
                projection_run_status=FollowUpTaskProjectionStatus.FAILED,
                error_message=failed_run.error_message,
            )

        duration_ms = _elapsed_ms(started_monotonic)
        if result.skip_reason is not None:
            completed_run = follow_up_task_projection_run_crud.mark_skipped(
                db,
                run,
                skip_reason=result.skip_reason,
                created_task_ids=result.created_task_ids,
                updated_task_ids=result.updated_task_ids,
                cancelled_task_ids=result.cancelled_task_ids,
                created_commitment_ids=result.created_commitment_ids,
                updated_commitment_ids=result.updated_commitment_ids,
                projection_hash=result.projection_hash,
                duration_ms=duration_ms,
                commit=False,
            )
            run_status = FollowUpTaskProjectionStatus.SKIPPED
        else:
            completed_run = follow_up_task_projection_run_crud.mark_success(
                db,
                run,
                created_task_ids=result.created_task_ids,
                updated_task_ids=result.updated_task_ids,
                cancelled_task_ids=result.cancelled_task_ids,
                created_commitment_ids=result.created_commitment_ids,
                updated_commitment_ids=result.updated_commitment_ids,
                projection_hash=result.projection_hash,
                duration_ms=duration_ms,
                commit=False,
            )
            run_status = FollowUpTaskProjectionStatus.SUCCESS

        if commit:
            db.commit()
            db.refresh(completed_run)

        _log_projection_run_result(
            db,
            activity_id=activity_id,
            trigger_type=trigger_type,
            run=completed_run,
            status=run_status,
            skip_reason=result.skip_reason,
            task_ids=result.created_task_ids + result.updated_task_ids + result.cancelled_task_ids,
            error_message=None,
        )

        return FollowUpTaskProjectionResult(
            trigger_type=result.trigger_type,
            source_type=result.source_type,
            source_key=result.source_key,
            input_snapshot_hash=result.input_snapshot_hash,
            projection_hash=result.projection_hash,
            skip_reason=result.skip_reason,
            created_task_ids=result.created_task_ids,
            updated_task_ids=result.updated_task_ids,
            cancelled_task_ids=result.cancelled_task_ids,
            created_commitment_ids=result.created_commitment_ids,
            updated_commitment_ids=result.updated_commitment_ids,
            projection_run_id=completed_run.id,
            projection_run_status=run_status,
        )

    def retry_projection_run(
        self,
        db: Session,
        *,
        projection_run_id: int,
        actor_id: str | None = None,
        commit: bool = True,
    ) -> FollowUpTaskProjectionResult:
        failed_run = follow_up_task_projection_run_crud.get_by_id(db, projection_run_id)
        if failed_run is None:
            raise ValueError("投影运行不存在")
        if failed_run.status != FollowUpTaskProjectionStatus.FAILED:
            raise ValueError("只能重试 FAILED 状态的投影运行")
        if failed_run.source_type != FollowUpTaskSourceType.CUSTOMER_ACTIVITY or failed_run.source_activity_id is None:
            raise ValueError("当前仅支持重试客户活动来源的投影运行")

        return self.run_activity_projection(
            db,
            activity_id=failed_run.source_activity_id,
            trigger_type=failed_run.trigger_type,
            actor_id=actor_id or failed_run.actor_id,
            team_id=failed_run.team_id,
            attempt_count=failed_run.attempt_count + 1,
            commit=commit,
        )

    def project_activity(
        self,
        db: Session,
        *,
        activity_id: int,
        trigger_type: str,
        actor_id: str | None = None,
        activity_snapshot: CustomerActivity | None = None,
        commit: bool = True,
    ) -> FollowUpTaskProjectionResult:
        self._validate_trigger_type(trigger_type)

        activity = activity_snapshot or customer_activity_crud.get_by_id(db, activity_id)
        if activity is None:
            return FollowUpTaskProjectionResult(
                trigger_type=trigger_type,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=None,
                input_snapshot_hash=None,
                projection_hash=None,
                skip_reason=FollowUpTaskProjectionSkipReason.ACTIVITY_NOT_FOUND,
            )

        if trigger_type == FollowUpTaskProjectionTrigger.ACTIVITY_DELETED:
            result = self._cancel_open_source_state(
                db,
                activity=activity,
                trigger_type=trigger_type,
                actor_id=actor_id,
                reason=FollowUpTaskProjectionSkipReason.SOURCE_ACTIVITY_DELETED,
                commit=commit,
            )
            return result

        result = self._project_open_activity(
            db,
            activity=activity,
            trigger_type=trigger_type,
            actor_id=actor_id,
            commit=commit,
        )
        return result

    def _validate_trigger_type(self, trigger_type: str) -> None:
        if trigger_type not in {
            FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
            FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
            FollowUpTaskProjectionTrigger.ACTIVITY_UPDATED,
            FollowUpTaskProjectionTrigger.ACTIVITY_DELETED,
            FollowUpTaskProjectionTrigger.HISTORICAL_BACKFILL,
        }:
            raise ValueError("未知任务投影触发类型")

    def _record_missing_activity_run(
        self,
        db: Session,
        *,
        activity_id: int,
        trigger_type: str,
        actor_id: str | None,
        team_id: int,
        attempt_count: int,
        commit: bool,
    ) -> FollowUpTaskProjectionResult:
        started_monotonic = time.perf_counter()
        source_key = f"activity:{activity_id}"
        projection_hash = _stable_hash({"skip_reason": FollowUpTaskProjectionSkipReason.ACTIVITY_NOT_FOUND})
        run = follow_up_task_projection_run_crud.create_running(
            db,
            FollowUpTaskProjectionRunInternalCreate(
                team_id=team_id,
                trigger_type=trigger_type,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=source_key,
                source_activity_id=activity_id,
                actor_id=actor_id,
                input_snapshot_hash=None,
                attempt_count=attempt_count,
            ),
            commit=False,
        )
        run = follow_up_task_projection_run_crud.mark_skipped(
            db,
            run,
            skip_reason=FollowUpTaskProjectionSkipReason.ACTIVITY_NOT_FOUND,
            projection_hash=projection_hash,
            duration_ms=_elapsed_ms(started_monotonic),
            commit=False,
        )
        if commit:
            db.commit()
            db.refresh(run)
        _log_projection_run_result(
            db,
            activity_id=activity_id,
            trigger_type=trigger_type,
            run=run,
            status=FollowUpTaskProjectionStatus.SKIPPED,
            skip_reason=FollowUpTaskProjectionSkipReason.ACTIVITY_NOT_FOUND,
            task_ids=[],
            error_message=None,
        )
        return FollowUpTaskProjectionResult(
            trigger_type=trigger_type,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=source_key,
            input_snapshot_hash=None,
            projection_hash=projection_hash,
            skip_reason=FollowUpTaskProjectionSkipReason.ACTIVITY_NOT_FOUND,
            projection_run_id=run.id,
            projection_run_status=FollowUpTaskProjectionStatus.SKIPPED,
        )

    def _project_open_activity(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        trigger_type: str,
        actor_id: str | None,
        commit: bool,
    ) -> FollowUpTaskProjectionResult:
        source_key = _activity_source_key(activity)
        input_snapshot = _activity_snapshot(activity)
        input_snapshot_hash = _stable_hash(input_snapshot)

        next_action = _clean_text(activity.next_action)
        due_at_text = _next_follow_time_text(activity)
        due_at_value = activity.next_follow_time

        if not next_action and due_at_value is None:
            result = self._cancel_open_source_state(
                db,
                activity=activity,
                trigger_type=trigger_type,
                actor_id=actor_id,
                reason=FollowUpTaskProjectionSkipReason.SOURCE_NEXT_STEP_REMOVED,
                commit=False,
            )
            if result.task_count == 0 and result.commitment_count == 0:
                result = FollowUpTaskProjectionResult(
                    trigger_type=trigger_type,
                    source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                    source_key=source_key,
                    input_snapshot_hash=input_snapshot_hash,
                    projection_hash=_stable_hash({"skip_reason": FollowUpTaskProjectionSkipReason.NO_NEXT_STEP}),
                    skip_reason=FollowUpTaskProjectionSkipReason.NO_NEXT_STEP,
                )
            if commit:
                db.commit()
            return result

        normalized_due_at = normalize_due_at(
            due_at_value,
            granularity=_infer_due_at_granularity(due_at_value),
        )
        title = next_action or "跟进客户进展"
        description = _clean_text(activity.summary) or _clean_text(activity.source_content)
        confidence = 1.0 if next_action and due_at_value is not None else 0.6
        evidence_json = _evidence_payload(activity, due_at_text=due_at_text, has_explicit_action=bool(next_action))
        commitment_projection = {
            "title": title,
            "content": next_action or description or title,
            "due_at": normalized_due_at.due_at.isoformat() if normalized_due_at.due_at else None,
            "due_at_text": due_at_text,
            "due_at_granularity": normalized_due_at.due_at_granularity,
            "confidence": confidence,
        }
        task_projection = None
        if normalized_due_at.due_at is not None:
            task_projection = {
                "title": title,
                "description": description,
                "due_at": normalized_due_at.due_at.isoformat(),
                "due_at_text": due_at_text,
                "due_at_granularity": normalized_due_at.due_at_granularity,
                "confidence": confidence,
            }
        projection_hash = _stable_hash(
            {
                "commitment": commitment_projection,
                "task": task_projection,
                "owner_id": activity.owner_id,
            }
        )

        created_commitment_ids, updated_commitment_ids = self._upsert_commitment(
            db,
            activity=activity,
            title=title,
            content=next_action or description or title,
            normalized_due_at=normalized_due_at,
            due_at_text=due_at_text,
            confidence=confidence,
            evidence_json=evidence_json,
        )

        if normalized_due_at.due_at is None:
            cancelled_result = self._cancel_open_tasks(
                db,
                activity=activity,
                actor_id=actor_id,
                reason=FollowUpTaskProjectionSkipReason.NO_DUE_AT,
            )
            self._sync_vector_documents(
                db,
                task_ids=cancelled_result,
                commitment_ids=created_commitment_ids + updated_commitment_ids,
            )
            if commit:
                db.commit()
            return FollowUpTaskProjectionResult(
                trigger_type=trigger_type,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=source_key,
                input_snapshot_hash=input_snapshot_hash,
                projection_hash=projection_hash,
                skip_reason=FollowUpTaskProjectionSkipReason.NO_DUE_AT,
                cancelled_task_ids=cancelled_result,
                created_commitment_ids=created_commitment_ids,
                updated_commitment_ids=updated_commitment_ids,
            )

        task_hash = _stable_hash(task_projection)
        existing_tasks = follow_up_task_crud.get_open_by_source(
            db,
            team_id=activity.team_id,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=source_key,
        )
        created_task_ids: list[int] = []
        updated_task_ids: list[int] = []
        cancelled_task_ids: list[int] = []
        commitment_id = (created_commitment_ids or updated_commitment_ids or [None])[0]
        if commitment_id is None:
            existing_commitments = sales_commitment_crud.get_open_by_source(
                db,
                team_id=activity.team_id,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=source_key,
            )
            commitment_id = existing_commitments[0].id if existing_commitments else None

        if existing_tasks:
            task = existing_tasks[0]
            duplicate_tasks = existing_tasks[1:]
            if task.owner_id != activity.owner_id:
                cancelled_task_ids.extend(
                    self._cancel_tasks(
                        db,
                        tasks=[task, *duplicate_tasks],
                        actor_id=actor_id,
                        reason="SOURCE_OWNER_CHANGED",
                    )
                )
                created_task = self._create_task(
                    db,
                    activity=activity,
                    title=title,
                    description=description,
                    due_at=normalized_due_at.due_at,
                    due_at_text=due_at_text,
                    due_at_granularity=normalized_due_at.due_at_granularity,
                    due_at_timezone=normalized_due_at.due_at_timezone,
                    confidence=confidence,
                    evidence_json=evidence_json,
                    task_hash=task_hash,
                    commitment_id=commitment_id,
                    actor_id=actor_id,
                )
                created_task_ids.append(created_task.id)
            else:
                if self._task_needs_update(
                    task,
                    title=title,
                    description=description,
                    due_at=normalized_due_at.due_at,
                    due_at_text=due_at_text,
                    due_at_granularity=normalized_due_at.due_at_granularity,
                    due_at_timezone=normalized_due_at.due_at_timezone,
                    confidence=confidence,
                    evidence_json=evidence_json,
                    task_hash=task_hash,
                    commitment_id=commitment_id,
                ):
                    previous_status = task.status
                    previous_payload = _task_event_payload(task)
                    follow_up_task_crud.update(
                        db,
                        task,
                        {
                            "commitment_id": commitment_id,
                            "title": title,
                            "description": description,
                            "due_at": normalized_due_at.due_at,
                            "due_at_text": due_at_text,
                            "due_at_granularity": normalized_due_at.due_at_granularity,
                            "due_at_timezone": normalized_due_at.due_at_timezone,
                            "confidence": confidence,
                            "evidence_json": evidence_json,
                            "task_hash": task_hash,
                        },
                        commit=False,
                    )
                    follow_up_task_event_crud.record_status_change(
                        db,
                        task=task,
                        event_type=FollowUpTaskEventType.UPDATED,
                        actor_id=actor_id,
                        previous_status=previous_status,
                        payload_json={
                            "reason": "SOURCE_ACTIVITY_UPDATED",
                            "previous": previous_payload,
                            "current": _task_event_payload(task),
                        },
                        commit=False,
                    )
                    updated_task_ids.append(task.id)
                cancelled_task_ids.extend(
                    self._cancel_tasks(
                        db,
                        tasks=duplicate_tasks,
                        actor_id=actor_id,
                        reason="DUPLICATE_SOURCE_TASK",
                    )
                )
        else:
            created_task = self._create_task(
                db,
                activity=activity,
                title=title,
                description=description,
                due_at=normalized_due_at.due_at,
                due_at_text=due_at_text,
                due_at_granularity=normalized_due_at.due_at_granularity,
                due_at_timezone=normalized_due_at.due_at_timezone,
                confidence=confidence,
                evidence_json=evidence_json,
                task_hash=task_hash,
                commitment_id=commitment_id,
                actor_id=actor_id,
            )
            created_task_ids.append(created_task.id)

        skip_reason = None
        if not created_task_ids and not updated_task_ids and not cancelled_task_ids and not created_commitment_ids and not updated_commitment_ids:
            skip_reason = FollowUpTaskProjectionSkipReason.NO_CHANGE

        self._sync_vector_documents(
            db,
            task_ids=created_task_ids + updated_task_ids + cancelled_task_ids,
            commitment_ids=created_commitment_ids + updated_commitment_ids,
        )

        if commit:
            db.commit()

        return FollowUpTaskProjectionResult(
            trigger_type=trigger_type,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=source_key,
            input_snapshot_hash=input_snapshot_hash,
            projection_hash=projection_hash,
            skip_reason=skip_reason,
            created_task_ids=created_task_ids,
            updated_task_ids=updated_task_ids,
            cancelled_task_ids=cancelled_task_ids,
            created_commitment_ids=created_commitment_ids,
            updated_commitment_ids=updated_commitment_ids,
        )

    def _upsert_commitment(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        title: str,
        content: str,
        normalized_due_at,
        due_at_text: str | None,
        confidence: float,
        evidence_json: dict[str, Any],
    ) -> tuple[list[int], list[int]]:
        source_key = _activity_source_key(activity)
        commitment_hash = _stable_hash(
            {
                "title": title,
                "content": content,
                "due_at": normalized_due_at.due_at.isoformat() if normalized_due_at.due_at else None,
                "due_at_text": due_at_text,
                "due_at_granularity": normalized_due_at.due_at_granularity,
            }
        )
        existing_commitments = sales_commitment_crud.get_open_by_source(
            db,
            team_id=activity.team_id,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=source_key,
        )
        if existing_commitments:
            commitment = existing_commitments[0]
            if self._commitment_needs_update(
                commitment,
                title=title,
                content=content,
                due_at=normalized_due_at.due_at,
                due_at_text=due_at_text,
                due_at_granularity=normalized_due_at.due_at_granularity,
                due_at_timezone=normalized_due_at.due_at_timezone,
                confidence=confidence,
                evidence_json=evidence_json,
                commitment_hash=commitment_hash,
            ):
                sales_commitment_crud.update(
                    db,
                    commitment,
                    {
                        "title": title,
                        "content": content,
                        "due_at": normalized_due_at.due_at,
                        "due_at_text": due_at_text,
                        "due_at_granularity": normalized_due_at.due_at_granularity,
                        "due_at_timezone": normalized_due_at.due_at_timezone,
                        "confidence": confidence,
                        "evidence_json": evidence_json,
                        "commitment_hash": commitment_hash,
                    },
                    commit=False,
                )
                return [], [commitment.id]
            return [], []

        commitment = sales_commitment_crud.create(
            db,
            SalesCommitmentInternalCreate(
                team_id=activity.team_id,
                customer_id=activity.customer_id,
                owner_id=activity.owner_id,
                creator_id=activity.creator_id,
                title=title,
                content=content,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=source_key,
                source_activity_id=activity.id,
                due_at=normalized_due_at.due_at,
                due_at_text=due_at_text,
                due_at_granularity=normalized_due_at.due_at_granularity,
                due_at_timezone=normalized_due_at.due_at_timezone,
                confidence=confidence,
                evidence_json=evidence_json,
                commitment_hash=commitment_hash,
            ),
            commit=False,
        )
        return [commitment.id], []

    def _create_task(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        title: str,
        description: str | None,
        due_at: datetime,
        due_at_text: str | None,
        due_at_granularity: str,
        due_at_timezone: str,
        confidence: float,
        evidence_json: dict[str, Any],
        task_hash: str,
        commitment_id: int | None,
        actor_id: str | None,
    ) -> FollowUpTask:
        task = follow_up_task_crud.create(
            db,
            FollowUpTaskInternalCreate(
                team_id=activity.team_id,
                customer_id=activity.customer_id,
                commitment_id=commitment_id,
                owner_id=activity.owner_id,
                creator_id=activity.creator_id,
                title=title,
                description=description,
                due_at=due_at,
                due_at_text=due_at_text,
                due_at_granularity=due_at_granularity,
                due_at_timezone=due_at_timezone,
                source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                source_key=_activity_source_key(activity),
                source_activity_id=activity.id,
                confidence=confidence,
                evidence_json=evidence_json,
                task_hash=task_hash,
            ),
            commit=False,
        )
        follow_up_task_event_crud.record_status_change(
            db,
            task=task,
            event_type=FollowUpTaskEventType.CREATED,
            actor_id=actor_id,
            previous_status=None,
            payload_json={"reason": "SOURCE_ACTIVITY_PROJECTED", "current": _task_event_payload(task)},
            commit=False,
        )
        return task

    def _cancel_open_source_state(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        trigger_type: str,
        actor_id: str | None,
        reason: str,
        commit: bool,
    ) -> FollowUpTaskProjectionResult:
        source_key = _activity_source_key(activity)
        input_snapshot_hash = _stable_hash(_activity_snapshot(activity))
        cancelled_task_ids = self._cancel_open_tasks(db, activity=activity, actor_id=actor_id, reason=reason)
        updated_commitment_ids = self._cancel_open_commitments(db, activity=activity)
        self._sync_vector_documents(db, task_ids=cancelled_task_ids, commitment_ids=updated_commitment_ids)
        if commit:
            db.commit()
        return FollowUpTaskProjectionResult(
            trigger_type=trigger_type,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=source_key,
            input_snapshot_hash=input_snapshot_hash,
            projection_hash=_stable_hash(
                {
                    "reason": reason,
                    "cancelled_task_ids": cancelled_task_ids,
                    "updated_commitment_ids": updated_commitment_ids,
                }
            ),
            skip_reason=reason,
            cancelled_task_ids=cancelled_task_ids,
            updated_commitment_ids=updated_commitment_ids,
        )

    def _cancel_open_tasks(
        self,
        db: Session,
        *,
        activity: CustomerActivity,
        actor_id: str | None,
        reason: str,
    ) -> list[int]:
        tasks = follow_up_task_crud.get_open_by_source(
            db,
            team_id=activity.team_id,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=_activity_source_key(activity),
        )
        return self._cancel_tasks(db, tasks=tasks, actor_id=actor_id, reason=reason)

    def _cancel_tasks(
        self,
        db: Session,
        *,
        tasks: list[FollowUpTask],
        actor_id: str | None,
        reason: str,
    ) -> list[int]:
        cancelled_task_ids: list[int] = []
        for task in tasks:
            previous_status = task.status
            previous_payload = _task_event_payload(task)
            follow_up_task_crud.cancel(db, task, commit=False)
            follow_up_task_event_crud.record_status_change(
                db,
                task=task,
                event_type=FollowUpTaskEventType.CANCELLED,
                actor_id=actor_id,
                previous_status=previous_status,
                payload_json={"reason": reason, "previous": previous_payload},
                commit=False,
            )
            follow_up_task_confirmation_cleanup_service.cancel_pending_cases_for_task(
                db,
                team_id=task.team_id,
                task_id=task.id,
                actor_id=actor_id,
                reason=_confirmation_cancel_reason(reason),
                commit=False,
            )
            cancelled_task_ids.append(task.id)
        return cancelled_task_ids

    def _cancel_open_commitments(self, db: Session, *, activity: CustomerActivity) -> list[int]:
        commitments = sales_commitment_crud.get_open_by_source(
            db,
            team_id=activity.team_id,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=_activity_source_key(activity),
        )
        updated_commitment_ids: list[int] = []
        for commitment in commitments:
            sales_commitment_crud.update(
                db,
                commitment,
                {"status": SalesCommitmentStatus.CANCELLED},
                commit=False,
            )
            updated_commitment_ids.append(commitment.id)
        return updated_commitment_ids

    def _sync_vector_documents(
        self,
        db: Session,
        *,
        task_ids: list[int],
        commitment_ids: list[int],
    ) -> None:
        for commitment_id in dict.fromkeys(commitment_ids):
            commitment = sales_commitment_crud.get_by_id(db, commitment_id)
            if commitment is not None:
                customer_vector_document_service.upsert_sales_commitment(db, commitment, commit=False)
        for task_id in dict.fromkeys(task_ids):
            task = follow_up_task_crud.get_by_id(db, task_id)
            if task is not None:
                customer_vector_document_service.upsert_follow_up_task(db, task, commit=False)

    def _task_needs_update(
        self,
        task: FollowUpTask,
        *,
        title: str,
        description: str | None,
        due_at: datetime,
        due_at_text: str | None,
        due_at_granularity: str,
        due_at_timezone: str,
        confidence: float,
        evidence_json: dict[str, Any],
        task_hash: str,
        commitment_id: int | None,
    ) -> bool:
        return any(
            [
                task.title != title,
                task.description != description,
                task.due_at != due_at,
                task.due_at_text != due_at_text,
                task.due_at_granularity != due_at_granularity,
                task.due_at_timezone != due_at_timezone,
                task.confidence != confidence,
                task.evidence_json != evidence_json,
                task.task_hash != task_hash,
                task.commitment_id != commitment_id,
            ]
        )

    def _commitment_needs_update(
        self,
        commitment: SalesCommitment,
        *,
        title: str,
        content: str,
        due_at: datetime | None,
        due_at_text: str | None,
        due_at_granularity: str,
        due_at_timezone: str,
        confidence: float,
        evidence_json: dict[str, Any],
        commitment_hash: str,
    ) -> bool:
        return any(
            [
                commitment.title != title,
                commitment.content != content,
                commitment.due_at != due_at,
                commitment.due_at_text != due_at_text,
                commitment.due_at_granularity != due_at_granularity,
                commitment.due_at_timezone != due_at_timezone,
                commitment.confidence != confidence,
                commitment.evidence_json != evidence_json,
                commitment.commitment_hash != commitment_hash,
            ]
        )


def _activity_source_key(activity: CustomerActivity) -> str:
    return f"activity:{activity.id}"


def _activity_snapshot(activity: CustomerActivity) -> dict[str, Any]:
    return {
        "team_id": activity.team_id,
        "customer_id": activity.customer_id,
        "owner_id": activity.owner_id,
        "creator_id": activity.creator_id,
        "source_content": activity.source_content,
        "summary": activity.summary,
        "next_action": _clean_text(activity.next_action),
        "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
        "next_follow_time_source": activity.next_follow_time_source,
        "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
    }


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _elapsed_ms(started_monotonic: float) -> int:
    return max(0, int((time.perf_counter() - started_monotonic) * 1000))


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _next_follow_time_text(activity: CustomerActivity) -> str | None:
    if not activity.content_json:
        return None
    try:
        content = json.loads(activity.content_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(content, dict):
        return None
    value = content.get("next_follow_time_text")
    return _clean_text(str(value)) if value is not None else None


def _confirmation_cancel_reason(projection_reason: str) -> str:
    if projection_reason == FollowUpTaskProjectionSkipReason.SOURCE_ACTIVITY_DELETED:
        return FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_DELETED
    if projection_reason in {
        FollowUpTaskProjectionSkipReason.SOURCE_NEXT_STEP_REMOVED,
        FollowUpTaskProjectionSkipReason.NO_DUE_AT,
    }:
        return FollowUpTaskConfirmationCancelReason.SOURCE_NEXT_STEP_REMOVED
    return FollowUpTaskConfirmationCancelReason.SOURCE_TASK_SUPERSEDED


def _infer_due_at_granularity(value: datetime | None) -> str:
    if value is None:
        return DueAtGranularity.UNKNOWN
    if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
        return DueAtGranularity.DATE
    return DueAtGranularity.DATETIME


def _evidence_payload(activity: CustomerActivity, *, due_at_text: str | None, has_explicit_action: bool) -> dict[str, Any]:
    return {
        "source_type": FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        "activity_kind": activity.activity_kind,
        "activity_title": activity.title,
        "activity_summary": activity.summary,
        "activity_occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
        "next_follow_time_source": activity.next_follow_time_source,
        "next_follow_time_text": due_at_text,
        "has_explicit_action": has_explicit_action,
    }


def _task_event_payload(task: FollowUpTask) -> dict[str, Any]:
    return {
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "due_at_text": task.due_at_text,
        "due_at_granularity": task.due_at_granularity,
        "due_at_timezone": task.due_at_timezone,
        "confidence": task.confidence,
        "task_hash": task.task_hash,
    }


def _log_projection_run_result(
    db: Session,
    *,
    activity_id: int,
    trigger_type: str,
    run,
    status: str,
    skip_reason: str | None,
    task_ids: list[int],
    error_message: str | None,
) -> None:
    task_public_ids = follow_up_task_crud.list_public_ids_by_ids(
        db,
        team_id=run.team_id,
        task_ids=task_ids,
    )
    logger.info(
        "客户活动任务投影完成: trigger_type=%s activity_id=%s projection_run_public_id=%s projection_run_id=%s status=%s skip_reason=%s task_public_ids=%s error=%s",
        trigger_type,
        activity_id,
        run.public_id,
        run.id,
        status,
        skip_reason,
        task_public_ids,
        error_message,
    )


follow_up_task_projection_service = FollowUpTaskProjectionService()
