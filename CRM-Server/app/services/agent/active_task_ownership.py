"""Checkpoint-safe active Agent task ownership projection and arbitration.

The root runtime must keep the active task snapshot, display projection and
LangGraph interrupt as one ownership unit.  This module is the single seam for
validating that unit and for arbitrating ownership emitted by concurrent
application branches without querying mutable database state.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.models.agent import AgentTaskStatus
from app.services.agent.interrupts import AgentInterruptPayload, interrupt_from_waiting_task_snapshot
from app.services.agent.task_projection import agent_task_snapshot
from app.services.agent.types import JSONDict, coerce_json_dict, coerce_json_value


@dataclass(frozen=True)
class ActiveTaskOwnershipProjection:
    """One authoritative active-task ownership unit for a root checkpoint."""

    active_task_snapshot: JSONDict = field(default_factory=dict)
    task_projection: JSONDict = field(default_factory=dict)
    current_interrupt: AgentInterruptPayload | None = None
    rejection_event: JSONDict | None = None

    @property
    def rejected(self) -> bool:
        return self.rejection_event is not None


@dataclass(frozen=True)
class ActiveTaskOwnershipCandidate:
    """Ownership candidate emitted by one application or graph branch."""

    source: str
    active_task_snapshot: JSONDict = field(default_factory=dict)
    current_interrupt: AgentInterruptPayload | None = None
    rejection_event: JSONDict | None = None

    @classmethod
    def from_projection(
        cls,
        projection: ActiveTaskOwnershipProjection,
        *,
        source: str,
    ) -> ActiveTaskOwnershipCandidate:
        return cls(
            source=source,
            active_task_snapshot=projection.active_task_snapshot,
            current_interrupt=projection.current_interrupt,
            rejection_event=projection.rejection_event,
        )

    @classmethod
    def from_mapping(
        cls,
        value: object,
        *,
        source: str,
    ) -> ActiveTaskOwnershipCandidate:
        values = coerce_json_dict(value)
        interrupt = values.get("current_interrupt")
        rejection = values.get("ownership_rejection_event") or values.get("rejection_event")
        return cls(
            source=source,
            active_task_snapshot=coerce_json_dict(values.get("active_task_snapshot")),
            current_interrupt=coerce_json_dict(interrupt) if isinstance(interrupt, Mapping) else None,
            rejection_event=coerce_json_dict(rejection) if isinstance(rejection, Mapping) else None,
        )


class ActiveTaskOwnershipProjector:
    """Validate and arbitrate task ownership without DB/event rediscovery."""

    def project_task(
        self,
        task: object | None,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        source: str,
        interaction: Mapping[str, object] | None = None,
    ) -> ActiveTaskOwnershipProjection:
        return self.project_snapshot(
            agent_task_snapshot(task),
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            source=source,
            interaction=interaction,
        )

    def project_snapshot(
        self,
        snapshot_value: object,
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        source: str,
        interaction: Mapping[str, object] | None = None,
        current_interrupt: Mapping[str, object] | None = None,
    ) -> ActiveTaskOwnershipProjection:
        snapshot = coerce_json_dict(snapshot_value)
        if not snapshot:
            return self._reject("missing_active_task_snapshot", source=source)
        task_id = _optional_int(snapshot.get("id"))
        if not _has_owner(snapshot, team_id=team_id, user_id=user_id, session_id=session_id):
            return self._reject(
                "active_task_owner_mismatch",
                source=source,
                active_task_ids=[task_id] if task_id is not None else [],
            )
        if snapshot.get("status") != AgentTaskStatus.WAITING_USER:
            return self._reject(
                "active_task_not_waiting_user",
                source=source,
                active_task_ids=[task_id] if task_id is not None else [],
            )
        try:
            canonical_interrupt = interrupt_from_waiting_task_snapshot(
                snapshot,
                interaction=interaction,
            )
        except (TypeError, ValueError):
            return self._reject(
                "invalid_active_task_snapshot",
                source=source,
                active_task_ids=[task_id] if task_id is not None else [],
            )

        selected_interrupt = canonical_interrupt
        if current_interrupt is not None:
            supplied_interrupt = coerce_json_dict(current_interrupt)
            if not _interrupt_matches_snapshot(supplied_interrupt, snapshot):
                return self._reject(
                    "active_task_interrupt_mismatch",
                    source=source,
                    active_task_ids=[task_id] if task_id is not None else [],
                )
            selected_interrupt = supplied_interrupt
        return ActiveTaskOwnershipProjection(
            active_task_snapshot=snapshot,
            task_projection=task_projection_from_snapshot(snapshot),
            current_interrupt=selected_interrupt,
        )

    def arbitrate(
        self,
        candidates: list[ActiveTaskOwnershipCandidate],
        *,
        team_id: int,
        user_id: int,
        session_id: int,
        source: str,
    ) -> ActiveTaskOwnershipProjection:
        selected: tuple[ActiveTaskOwnershipCandidate, ActiveTaskOwnershipProjection] | None = None
        candidate_sources: list[str] = []
        active_task_ids: list[int] = []

        for candidate in candidates:
            if candidate.rejection_event:
                return ActiveTaskOwnershipProjection(rejection_event=candidate.rejection_event)
            if not candidate.active_task_snapshot and candidate.current_interrupt is None:
                continue
            if not candidate.active_task_snapshot:
                return self._reject(
                    "missing_active_task_snapshot",
                    source=source,
                    candidate_sources=[candidate.source],
                )
            projected = self.project_snapshot(
                candidate.active_task_snapshot,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                source=candidate.source,
                current_interrupt=candidate.current_interrupt,
            )
            if projected.rejected:
                return projected
            task_id = _optional_int(projected.active_task_snapshot.get("id"))
            if task_id is not None:
                active_task_ids.append(task_id)
            candidate_sources.append(candidate.source)
            if selected is None:
                selected = (candidate, projected)
                continue
            _, selected_projection = selected
            selected_task_id = _optional_int(selected_projection.active_task_snapshot.get("id"))
            if task_id != selected_task_id:
                return self._reject(
                    "multiple_active_tasks",
                    source=source,
                    active_task_ids=_unique_ints(active_task_ids),
                    candidate_sources=candidate_sources,
                )
            if (
                projected.active_task_snapshot != selected_projection.active_task_snapshot
                or projected.current_interrupt != selected_projection.current_interrupt
            ):
                return self._reject(
                    "active_task_projection_conflict",
                    source=source,
                    active_task_ids=_unique_ints(active_task_ids),
                    candidate_sources=candidate_sources,
                )

        if selected is None:
            return ActiveTaskOwnershipProjection()
        return selected[1]

    @staticmethod
    def _reject(
        reason: str,
        *,
        source: str,
        active_task_ids: list[int] | None = None,
        candidate_sources: list[str] | None = None,
    ) -> ActiveTaskOwnershipProjection:
        event: JSONDict = {
            "event": "agent_root_active_task_ownership_rejected",
            "reason": reason,
            "source": source,
        }
        if active_task_ids:
            event["active_task_ids"] = active_task_ids
        if candidate_sources:
            event["candidate_sources"] = candidate_sources
        return ActiveTaskOwnershipProjection(rejection_event=event)


def task_projection_from_snapshot(snapshot_value: object) -> JSONDict:
    """Return the display/audit projection belonging to one active snapshot."""

    snapshot = coerce_json_dict(snapshot_value)
    projection: JSONDict = {}
    for key in ("id", "task_key", "status", "intent", "target_type", "target_id"):
        if key in snapshot:
            projection[key] = coerce_json_value(snapshot[key])
    return projection


def _has_owner(snapshot: JSONDict, *, team_id: int, user_id: int, session_id: int) -> bool:
    return (
        _optional_int(snapshot.get("team_id")) == team_id
        and _optional_int(snapshot.get("user_id")) == user_id
        and _optional_int(snapshot.get("session_id")) == session_id
    )


def _interrupt_matches_snapshot(interrupt: JSONDict, snapshot: JSONDict) -> bool:
    if _optional_int(interrupt.get("task_projection_id")) != _optional_int(snapshot.get("id")):
        return False
    interrupt_key = interrupt.get("task_projection_key")
    snapshot_key = snapshot.get("task_key")
    return isinstance(interrupt_key, str) and interrupt_key == snapshot_key


def _unique_ints(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


active_task_ownership_projector = ActiveTaskOwnershipProjector()
