"""Durable, idempotent projection of PendingTask native interrupts.

The PendingTask checkpoint is the authoritative business outcome.  This module
turns that outcome into transactionally idempotent CRM persistence, stores a
JSON-safe replay result, and treats transport publication as a separate durable
outbox stage.  Root runtime callers therefore do not need to know transaction,
lease, replay, or event-delivery rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from hashlib import sha256
from typing import TYPE_CHECKING
from uuid import uuid4

from app.crud.agent import agent_task_crud
from app.crud.agent_pending_interrupt_projection import (
    AgentPendingInterruptProjectionCRUD,
    agent_pending_interrupt_projection_crud,
)
from app.models.agent_pending_interrupt_projection import (
    AgentPendingInterruptDeliveryStatus,
    AgentPendingInterruptProjectionStatus,
)
from app.services.agent.pending_continuation import (
    PendingTaskContinuationRef,
    pending_task_continuation_from_json,
)
from app.services.agent.pending_effects import (
    PendingTaskSideEffectContext,
    PendingTaskSideEffectHandler,
    pending_task_side_effect_handler,
)
from app.services.agent.state import PendingTaskGraphResult, PendingTaskGraphSideEffects
from app.services.agent.task_projection import agent_task_snapshot
from app.services.agent.types import AgentRuntimeEventSink, JSONDict, coerce_json_dict
from app.utils.time import business_now

if TYPE_CHECKING:
    from app.services.agent.interrupts import AgentInterruptPayload


@dataclass(frozen=True)
class PendingInterruptProjectionRequest:
    db: object
    session: object
    team_id: int
    user_id: int
    session_id: int
    root_thread_id: str
    continuation: PendingTaskContinuationRef
    interrupt: AgentInterruptPayload
    outcome: PendingTaskGraphResult
    task: object | None = None
    switch_notice: str | None = None
    event_sink: AgentRuntimeEventSink | None = None


@dataclass
class PendingInterruptProjectionResult:
    status: str
    projection_key: str
    replayed: bool = False
    busy: bool = False
    retryable: bool = False
    failure_reason: str | None = None
    task: object | None = None
    suspended_task: object | None = None
    task_snapshot: JSONDict = field(default_factory=dict)
    suspended_task_snapshot: JSONDict = field(default_factory=dict)
    events: list[JSONDict] = field(default_factory=list)
    assistant_content: str | None = None
    switch_notice: str | None = None
    current_interrupt: AgentInterruptPayload | None = None
    delivery_status: str | None = None


class PendingInterruptProjector:
    """Deep module owning child-checkpoint-to-CRM projection semantics."""

    def __init__(
        self,
        *,
        crud: AgentPendingInterruptProjectionCRUD = agent_pending_interrupt_projection_crud,
        side_effect_handler: PendingTaskSideEffectHandler = pending_task_side_effect_handler,
        lease_seconds: int = 60,
    ) -> None:
        self.crud = crud
        self.side_effect_handler = side_effect_handler
        self.lease_seconds = max(5, lease_seconds)

    async def project(self, request: PendingInterruptProjectionRequest) -> PendingInterruptProjectionResult:
        failure = _validate_request(request)
        projection_key = pending_interrupt_projection_key(request.continuation, request.interrupt)
        if failure:
            return PendingInterruptProjectionResult(
                status="FAILED",
                projection_key=projection_key,
                failure_reason=failure,
            )
        if not _supports_persistence(request.db):
            return await self._project_ephemeral(request, projection_key=projection_key)

        record = self.crud.ensure(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            session_id=request.session_id,
            task_id=request.continuation.get("task_id"),
            projection_key=projection_key,
            continuation_json=coerce_json_dict(request.continuation),
            interrupt_json=coerce_json_dict(request.interrupt),
        )
        record_failure = _validate_record_identity(record, request)
        if record_failure:
            return PendingInterruptProjectionResult(
                status="FAILED",
                projection_key=projection_key,
                failure_reason=record_failure,
            )
        if record.status == AgentPendingInterruptProjectionStatus.PROJECTED:
            result = _result_from_json(record.result_json, projection_key=projection_key, replayed=True)
            result.task = _reload_projected_task(request, result.task_snapshot.get("id"))
            result.suspended_task = _reload_projected_task(
                request,
                result.suspended_task_snapshot.get("id"),
            )
            result.delivery_status = await self._deliver_record(request, projection_key, result.events)
            return result

        lease_token = uuid4().hex
        claimed = self.crud.claim_projection(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            projection_key=projection_key,
            lease_token=lease_token,
            lease_expires_at=business_now() + timedelta(seconds=self.lease_seconds),
        )
        if claimed is None:
            latest = self.crud.get_by_key(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                projection_key=projection_key,
            )
            if latest is not None and latest.status == AgentPendingInterruptProjectionStatus.PROJECTED:
                result = _result_from_json(latest.result_json, projection_key=projection_key, replayed=True)
                result.task = _reload_projected_task(request, result.task_snapshot.get("id"))
                result.suspended_task = _reload_projected_task(
                    request,
                    result.suspended_task_snapshot.get("id"),
                )
                result.delivery_status = await self._deliver_record(request, projection_key, result.events)
                return result
            return PendingInterruptProjectionResult(
                status="IN_PROGRESS",
                projection_key=projection_key,
                busy=True,
                retryable=True,
                failure_reason="projection_in_progress",
            )

        try:
            result = self._apply_business_projection(request, projection_key=projection_key)
            result_json = _result_to_json(result)
            completed = self.crud.mark_projected_if_lease_owner(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                projection_key=projection_key,
                lease_token=lease_token,
                result_json=result_json,
                commit=False,
            )
            if completed is None:
                raise RuntimeError("pending interrupt projection lease lost before completion")
            request.db.commit()
        except Exception as exc:
            _rollback(request.db)
            self.crud.mark_projection_failed_if_lease_owner(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                projection_key=projection_key,
                lease_token=lease_token,
                error_message=str(exc),
            )
            return PendingInterruptProjectionResult(
                status="FAILED",
                projection_key=projection_key,
                failure_reason="projection_failed",
            )

        result.delivery_status = await self._deliver_record(request, projection_key, result.events)
        return result

    async def _project_ephemeral(
        self,
        request: PendingInterruptProjectionRequest,
        *,
        projection_key: str,
    ) -> PendingInterruptProjectionResult:
        """Compatibility adapter for tests/non-SQL runtimes, with no durability claim."""

        result = self._apply_business_projection(
            request,
            projection_key=projection_key,
            commit=True,
        )
        if request.event_sink is None:
            result.delivery_status = AgentPendingInterruptDeliveryStatus.INLINE_VISIBLE
        else:
            try:
                for event in result.events:
                    await request.event_sink(event)
                result.delivery_status = AgentPendingInterruptDeliveryStatus.DELIVERED
            except Exception:
                result.delivery_status = AgentPendingInterruptDeliveryStatus.FAILED
        return result

    def _apply_business_projection(
        self,
        request: PendingInterruptProjectionRequest,
        *,
        projection_key: str,
        commit: bool = False,
    ) -> PendingInterruptProjectionResult:
        task = request.task
        if task is None and request.continuation.get("task_id") is not None:
            task = agent_task_crud.get_by_id(
                request.db,
                int(request.continuation["task_id"]),
                team_id=request.team_id,
                user_id=request.user_id,
            )
        graph_side_effects = PendingTaskGraphSideEffects(task=task)
        applied = self.side_effect_handler.apply(
            request.outcome,
            PendingTaskSideEffectContext(
                db=request.db,
                session=request.session,
                team_id=request.team_id,
                user_id=request.user_id,
                task=task,
                switch_notice=request.switch_notice,
                graph_side_effects=graph_side_effects,
                commit=commit,
            ),
        )
        stable_events = [
            {
                **coerce_json_dict(event),
                "projection_key": projection_key,
                "projection_event_id": f"{projection_key}:{index}",
            }
            for index, event in enumerate(applied.events)
        ]
        return PendingInterruptProjectionResult(
            status="PROJECTED",
            projection_key=projection_key,
            task=applied.task,
            suspended_task=getattr(applied, "suspended_task", None),
            task_snapshot=agent_task_snapshot(applied.task),
            suspended_task_snapshot=agent_task_snapshot(
                getattr(applied, "suspended_task", None)
            ),
            events=stable_events,
            assistant_content=applied.assistant_content,
            switch_notice=applied.switch_notice,
            current_interrupt=applied.current_interrupt or request.interrupt,
        )

    async def _deliver_record(
        self,
        request: PendingInterruptProjectionRequest,
        projection_key: str,
        events: list[JSONDict],
    ) -> str:
        if request.event_sink is None:
            return await self._finish_delivery_without_transport(
                request,
                projection_key,
                AgentPendingInterruptDeliveryStatus.INLINE_VISIBLE,
                reason_code="RETURNED_IN_RUNTIME_OUTCOME",
            )
        lease_token = uuid4().hex
        claimed = self.crud.claim_delivery(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            projection_key=projection_key,
            lease_token=lease_token,
            lease_expires_at=business_now() + timedelta(seconds=self.lease_seconds),
        )
        if claimed is None:
            latest = self.crud.get_by_key(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                projection_key=projection_key,
            )
            return str(getattr(latest, "delivery_status", None) or "PENDING")
        try:
            for event in events:
                await request.event_sink(event)
        except Exception as exc:
            return self._finish_delivery_and_read_status(
                request,
                projection_key,
                lease_token=lease_token,
                status=AgentPendingInterruptDeliveryStatus.FAILED,
                error_message=str(exc),
                reason_code="EVENT_SINK_EXCEPTION",
            )
        return self._finish_delivery_and_read_status(
            request,
            projection_key,
            lease_token=lease_token,
            status=AgentPendingInterruptDeliveryStatus.DELIVERED,
            reason_code="EVENT_SINK_ACCEPTED",
        )

    async def _finish_delivery_without_transport(
        self,
        request: PendingInterruptProjectionRequest,
        projection_key: str,
        status: str,
        *,
        reason_code: str,
    ) -> str:
        lease_token = uuid4().hex
        claimed = self.crud.claim_delivery(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            projection_key=projection_key,
            lease_token=lease_token,
            lease_expires_at=business_now() + timedelta(seconds=self.lease_seconds),
        )
        if claimed is None:
            latest = self.crud.get_by_key(
                request.db,
                team_id=request.team_id,
                user_id=request.user_id,
                projection_key=projection_key,
            )
            return str(getattr(latest, "delivery_status", None) or "PENDING")
        return self._finish_delivery_and_read_status(
            request,
            projection_key,
            lease_token=lease_token,
            status=status,
            reason_code=reason_code,
        )

    def _finish_delivery_and_read_status(
        self,
        request: PendingInterruptProjectionRequest,
        projection_key: str,
        *,
        lease_token: str,
        status: str,
        reason_code: str,
        error_message: str | None = None,
    ) -> str:
        finished = self.crud.finish_delivery_if_lease_owner(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            projection_key=projection_key,
            lease_token=lease_token,
            status=status,
            error_message=error_message,
            reason_code=reason_code,
        )
        if finished is not None:
            return str(finished.delivery_status)

        # The transport may have accepted the event after this worker lost its
        # lease. Never report the desired terminal state unless it is durable.
        latest = self.crud.get_by_key(
            request.db,
            team_id=request.team_id,
            user_id=request.user_id,
            projection_key=projection_key,
        )
        return str(getattr(latest, "delivery_status", None) or "PENDING")


def pending_interrupt_projection_key(
    continuation: PendingTaskContinuationRef,
    interrupt: AgentInterruptPayload,
) -> str:
    """Return a fixed-length idempotency key over the full authenticated identity."""

    interaction = coerce_json_dict(interrupt.get("interaction"))
    semantic_identity = {
        "continuation": coerce_json_dict(continuation),
        "interrupt_identity": {
            "interaction_id": interaction.get("interaction_id"),
            "interrupt_id": interrupt.get("interrupt_id"),
            "source_event": interrupt.get("source_event"),
            "business_action": interrupt.get("business_action"),
            "reason": interrupt.get("reason"),
        },
    }
    if not any(semantic_identity["interrupt_identity"].values()):
        semantic_identity["interrupt_identity"] = coerce_json_dict(interrupt)
    digest = sha256(
        json.dumps(semantic_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"pending_interrupt_projection:v1:{digest}"


def _validate_request(request: PendingInterruptProjectionRequest) -> str | None:
    continuation = pending_task_continuation_from_json(
        request.continuation,
        expected_team_id=request.team_id,
        expected_user_id=request.user_id,
        expected_session_id=request.session_id,
        expected_thread_id=request.root_thread_id,
    )
    if continuation is None:
        return "invalid_continuation"
    interrupt_continuation = pending_task_continuation_from_json(
        request.interrupt.get("checkpoint_ref"),
        expected_team_id=request.team_id,
        expected_user_id=request.user_id,
        expected_session_id=request.session_id,
        expected_thread_id=request.root_thread_id,
    )
    if interrupt_continuation != continuation:
        return "interrupt_continuation_mismatch"
    return None


def _validate_record_identity(record: object, request: PendingInterruptProjectionRequest) -> str | None:
    if getattr(record, "session_id", None) != request.session_id:
        return "projection_session_mismatch"
    if getattr(record, "task_id", None) != request.continuation.get("task_id"):
        return "projection_task_mismatch"
    if coerce_json_dict(getattr(record, "continuation_json", None)) != coerce_json_dict(request.continuation):
        return "projection_continuation_mismatch"
    return None


def _reload_projected_task(
    request: PendingInterruptProjectionRequest,
    task_id: object,
) -> object | None:
    """Reload a replayed ORM projection without treating it as graph truth."""

    if not isinstance(task_id, int):
        return None
    task = agent_task_crud.get_by_id(
        request.db,
        task_id,
        team_id=request.team_id,
        user_id=request.user_id,
    )
    if task is None or getattr(task, "session_id", None) != request.session_id:
        return None
    return task


def _result_to_json(result: PendingInterruptProjectionResult) -> JSONDict:
    task_snapshot = result.task_snapshot or agent_task_snapshot(result.task)
    suspended_task_snapshot = (
        result.suspended_task_snapshot or agent_task_snapshot(result.suspended_task)
    )
    return coerce_json_dict(
        {
            "status": result.status,
            "projection_key": result.projection_key,
            "task_id": task_snapshot.get("id"),
            "suspended_task_id": suspended_task_snapshot.get("id"),
            "task_snapshot": task_snapshot,
            "suspended_task_snapshot": suspended_task_snapshot,
            "events": result.events,
            "assistant_content": result.assistant_content,
            "switch_notice": result.switch_notice,
            "current_interrupt": result.current_interrupt,
        }
    )


def _result_from_json(
    value: object,
    *,
    projection_key: str,
    replayed: bool,
) -> PendingInterruptProjectionResult:
    payload = coerce_json_dict(value)
    events = payload.get("events")
    return PendingInterruptProjectionResult(
        status=str(payload.get("status") or "PROJECTED"),
        projection_key=projection_key,
        replayed=replayed,
        task_snapshot=coerce_json_dict(payload.get("task_snapshot")),
        suspended_task_snapshot=coerce_json_dict(payload.get("suspended_task_snapshot")),
        events=(
            [coerce_json_dict(event) for event in events if isinstance(event, dict)] if isinstance(events, list) else []
        ),
        assistant_content=(
            payload.get("assistant_content") if isinstance(payload.get("assistant_content"), str) else None
        ),
        switch_notice=payload.get("switch_notice") if isinstance(payload.get("switch_notice"), str) else None,
        current_interrupt=coerce_json_dict(payload.get("current_interrupt")) or None,
    )


def _supports_persistence(db: object) -> bool:
    return all(callable(getattr(db, name, None)) for name in ("query", "add", "commit", "flush"))


def _rollback(db: object) -> None:
    rollback = getattr(db, "rollback", None)
    if callable(rollback):
        rollback()


# Outcome-oriented public contract. The legacy interrupt names remain aliases
# because the durable table and existing integrations predate terminal outcome
# barriers; both child interrupts and terminal outcomes share one projection
# state machine, lease, idempotency key, and delivery outbox.
PendingTaskOutcomeProjectionRequest = PendingInterruptProjectionRequest
PendingTaskOutcomeProjectionResult = PendingInterruptProjectionResult
PendingTaskOutcomeProjector = PendingInterruptProjector

pending_interrupt_projector = PendingInterruptProjector()
pending_task_outcome_projector = pending_interrupt_projector
