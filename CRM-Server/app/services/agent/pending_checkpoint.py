"""Durable checkpoint adapter for the pending-task LangGraph.

The root runtime must not know how a checkpointer represents channel state or
pending interrupt writes. This adapter is the persistence seam: it resolves an
exact child continuation reference and returns checkpoint-safe business state.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from langgraph.types import Interrupt

from app.services.agent.types import coerce_json_dict

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from app.services.agent.interrupts import AgentInterruptPayload
    from app.services.agent.pending_continuation import PendingTaskContinuationRef

_INTERRUPT_CHANNEL = "__interrupt__"
logger = logging.getLogger(__name__)


class AsyncCheckpointReader(Protocol):
    """Public subset of LangGraph's checkpoint saver used by this adapter."""

    async def aget_tuple(self, config: RunnableConfig) -> object | None: ...


class PendingTaskCheckpointRepository(Protocol):
    """Persistence seam consumed by pending-task orchestration."""

    @property
    def enabled(self) -> bool: ...

    async def load_result(
        self,
        checkpoint_ref: PendingTaskContinuationRef,
        *,
        expected_interrupt: AgentInterruptPayload | None = None,
    ) -> PendingTaskCheckpointLoadResult: ...


@dataclass(frozen=True)
class PendingTaskCheckpointSnapshot:
    """Authoritative, storage-independent view of a child checkpoint."""

    ref: PendingTaskContinuationRef
    values: dict[str, object]
    interrupts: tuple[Interrupt, ...]


@dataclass(frozen=True)
class PendingTaskCheckpointLoadResult:
    """Structured checkpoint recovery result for fail-closed orchestration."""

    snapshot: PendingTaskCheckpointSnapshot | None = None
    failure_reason: str | None = None


class PendingTaskCheckpointStore:
    """Resolve pending-task state through LangGraph's public saver interface."""

    def __init__(self, checkpointer: object | None) -> None:
        self._reader = _as_checkpoint_reader(checkpointer)

    @property
    def enabled(self) -> bool:
        return self._reader is not None

    async def load_result(
        self,
        checkpoint_ref: PendingTaskContinuationRef,
        *,
        expected_interrupt: AgentInterruptPayload | None = None,
    ) -> PendingTaskCheckpointLoadResult:
        """Resolve one exact V2 root-owned continuation; never scan namespaces."""

        reader = self._reader
        if reader is None:
            return PendingTaskCheckpointLoadResult(failure_reason="checkpoint_store_unavailable")

        exact_config = _checkpoint_config(checkpoint_ref)
        try:
            checkpoint_tuple = await reader.aget_tuple(exact_config)
        except Exception:
            logger.exception(
                "Failed to load exact pending-task checkpoint",
                extra={
                    "thread_id": checkpoint_ref["thread_id"],
                    "checkpoint_ns": checkpoint_ref["checkpoint_ns"],
                },
            )
            return PendingTaskCheckpointLoadResult(
                failure_reason="checkpoint_recovery_exception"
            )
        if checkpoint_tuple is None:
            return PendingTaskCheckpointLoadResult(
                failure_reason="checkpoint_locator_not_found"
            )
        snapshot = _snapshot_from_tuple(checkpoint_tuple, checkpoint_ref)
        if snapshot is None:
            return PendingTaskCheckpointLoadResult(failure_reason="checkpoint_corrupt")
        if not _snapshot_matches(snapshot, expected_interrupt):
            return PendingTaskCheckpointLoadResult(
                failure_reason="checkpoint_interrupt_not_found"
            )
        return PendingTaskCheckpointLoadResult(snapshot=snapshot)


def _as_checkpoint_reader(checkpointer: object | None) -> AsyncCheckpointReader | None:
    if checkpointer is None:
        return None
    if not callable(getattr(checkpointer, "aget_tuple", None)):
        return None
    return cast("AsyncCheckpointReader", checkpointer)


def _checkpoint_config(checkpoint_ref: PendingTaskContinuationRef) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": checkpoint_ref["thread_id"],
            "checkpoint_ns": checkpoint_ref["checkpoint_ns"],
        }
    }


def _snapshot_from_tuple(
    checkpoint_tuple: object | None,
    requested_ref: PendingTaskContinuationRef,
) -> PendingTaskCheckpointSnapshot | None:
    if checkpoint_tuple is None:
        return None
    if not _tuple_matches_requested_ref(
        getattr(checkpoint_tuple, "config", None),
        requested_ref,
    ):
        return None
    checkpoint = getattr(checkpoint_tuple, "checkpoint", None)
    if not isinstance(checkpoint, Mapping):
        return None
    channel_values = checkpoint.get("channel_values")
    if not isinstance(channel_values, Mapping):
        return None
    values = {str(key): value for key, value in channel_values.items() if isinstance(key, str)}
    interrupts = _interrupts_from_checkpoint_tuple(checkpoint_tuple, values)
    return PendingTaskCheckpointSnapshot(
        ref={**requested_ref},
        values=values,
        interrupts=interrupts,
    )


def _tuple_matches_requested_ref(
    config: object,
    requested_ref: PendingTaskContinuationRef,
) -> bool:
    configurable = coerce_json_dict(coerce_json_dict(config).get("configurable"))
    return (
        configurable.get("thread_id") == requested_ref["thread_id"]
        and configurable.get("checkpoint_ns") == requested_ref["checkpoint_ns"]
    )


def _interrupts_from_checkpoint_tuple(
    checkpoint_tuple: object,
    values: Mapping[str, object],
) -> tuple[Interrupt, ...]:
    found: list[Interrupt] = []
    _append_interrupts(found, values.get(_INTERRUPT_CHANNEL))
    pending_writes = getattr(checkpoint_tuple, "pending_writes", None)
    if isinstance(pending_writes, Sequence) and not isinstance(pending_writes, str | bytes):
        for pending_write in pending_writes:
            if not isinstance(pending_write, Sequence) or isinstance(pending_write, str | bytes):
                continue
            if len(pending_write) < 3 or pending_write[1] != _INTERRUPT_CHANNEL:
                continue
            _append_interrupts(found, pending_write[2])
    return tuple(_deduplicate_interrupts(found))


def _append_interrupts(target: list[Interrupt], value: object) -> None:
    if isinstance(value, Interrupt):
        target.append(value)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            _append_interrupts(target, item)


def _deduplicate_interrupts(interrupts: Sequence[Interrupt]) -> list[Interrupt]:
    result: list[Interrupt] = []
    seen: set[str] = set()
    for interrupt_item in interrupts:
        identity = interrupt_item.id or repr(interrupt_item.value)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(interrupt_item)
    return result


def _snapshot_matches(
    snapshot: PendingTaskCheckpointSnapshot | None,
    expected_interrupt: AgentInterruptPayload | None,
) -> bool:
    if snapshot is None:
        return False
    if expected_interrupt is None:
        return True
    return any(
        _interrupt_payload_matches(interrupt_item.value, expected_interrupt) for interrupt_item in snapshot.interrupts
    )


def _interrupt_payload_matches(
    value: object,
    expected_interrupt: AgentInterruptPayload,
) -> bool:
    payload = coerce_json_dict(value)
    expected_interaction = coerce_json_dict(expected_interrupt.get("interaction"))
    interaction = coerce_json_dict(payload.get("interaction"))
    expected_interaction_id = expected_interaction.get("interaction_id")
    interaction_id = interaction.get("interaction_id")
    if expected_interaction_id:
        return bool(interaction_id) and expected_interaction_id == interaction_id
    identity_fields = ("source_event", "business_action", "task_projection_id")
    expected_identity = tuple(expected_interrupt.get(field) for field in identity_fields)
    if not any(value is not None for value in expected_identity):
        return False
    return tuple(payload.get(field) for field in identity_fields) == expected_identity
