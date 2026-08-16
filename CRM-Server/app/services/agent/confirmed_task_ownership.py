"""Checkpoint-safe ownership transfer after confirmed Agent task execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.agent.active_task_ownership import active_task_ownership_projector
from app.services.agent.task_projection import agent_task_snapshot
from app.services.agent.types import JSONDict, coerce_json_dict

if TYPE_CHECKING:
    from app.services.agent.interrupts import AgentInterruptPayload


@dataclass(frozen=True)
class ConfirmedTaskOwnershipProjection:
    """Authoritative active owner projected by one confirmed execution result."""

    active_task_snapshot: JSONDict = field(default_factory=dict)
    task_projection: JSONDict = field(default_factory=dict)
    current_interrupt: AgentInterruptPayload | None = None
    rejection_event: JSONDict | None = None

    @property
    def rejected(self) -> bool:
        return self.rejection_event is not None


class ConfirmedTaskOwnershipProjector:
    """Validate one ownership hand-off without querying mutable application state.

    The confirmed-task graph returns both the executed task and the only task
    allowed to become active next. This projector validates tenant/session
    ownership and produces the root checkpoint fields atomically. Transport
    events remain presentation/audit data and are never used to rediscover a
    task from the database.
    """

    def project(
        self,
        result_value: object,
        *,
        expected_task: object,
        team_id: int,
        user_id: int,
        session_id: int,
    ) -> ConfirmedTaskOwnershipProjection:
        result = coerce_json_dict(result_value)
        task_event = coerce_json_dict(result.get("task_event"))
        executed_snapshot = coerce_json_dict(result.get("executed_task_snapshot"))
        active_snapshot = coerce_json_dict(result.get("active_task_snapshot"))
        next_task_id = _optional_int(task_event.get("next_task_id"))
        expected_task_id = _optional_int(agent_task_snapshot(expected_task).get("id"))
        contract_declared = (
            "executed_task_snapshot" in result
            or "active_task_snapshot" in result
            or next_task_id is not None
        )

        def reject(reason: str) -> ConfirmedTaskOwnershipProjection:
            return ConfirmedTaskOwnershipProjection(
                rejection_event={
                    "event": "agent_root_confirmed_task_ownership_rejected",
                    "reason": reason,
                    "expected_task_id": expected_task_id,
                    "executed_task_id": _optional_int(executed_snapshot.get("id")),
                    "next_task_id": next_task_id,
                    "active_task_id": _optional_int(active_snapshot.get("id")),
                }
            )

        # A legacy adapter may clear ownership only when it declares no next
        # task. Once next_task_id exists, guessing from events/DB is forbidden.
        if not contract_declared:
            return ConfirmedTaskOwnershipProjection()
        if not executed_snapshot:
            return reject("missing_executed_task_snapshot")
        if expected_task_id is None or _optional_int(executed_snapshot.get("id")) != expected_task_id:
            return reject("executed_task_mismatch")
        if not _has_owner(
            executed_snapshot,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
        ):
            return reject("executed_task_owner_mismatch")

        if next_task_id is None and not active_snapshot:
            return ConfirmedTaskOwnershipProjection()
        if next_task_id is None:
            return reject("active_task_without_next_task_event")
        if not active_snapshot:
            return reject("next_task_missing_active_snapshot")
        active_task_id = _optional_int(active_snapshot.get("id"))
        if active_task_id != next_task_id:
            return reject("next_task_snapshot_mismatch")
        if active_task_id == expected_task_id:
            return reject("executed_task_cannot_remain_active")
        active_ownership = active_task_ownership_projector.project_snapshot(
            active_snapshot,
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            source="confirmed_task_handoff",
            interaction=coerce_json_dict(task_event.get("interaction")) or None,
        )
        if active_ownership.rejection_event:
            reason = active_ownership.rejection_event.get("reason")
            return reject(reason if isinstance(reason, str) else "invalid_active_task_snapshot")
        return ConfirmedTaskOwnershipProjection(
            active_task_snapshot=active_ownership.active_task_snapshot,
            task_projection=active_ownership.task_projection,
            current_interrupt=active_ownership.current_interrupt,
        )


def _has_owner(
    snapshot: JSONDict,
    *,
    team_id: int,
    user_id: int,
    session_id: int,
) -> bool:
    return (
        _optional_int(snapshot.get("team_id")) == team_id
        and _optional_int(snapshot.get("user_id")) == user_id
        and _optional_int(snapshot.get("session_id")) == session_id
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


confirmed_task_ownership_projector = ConfirmedTaskOwnershipProjector()
