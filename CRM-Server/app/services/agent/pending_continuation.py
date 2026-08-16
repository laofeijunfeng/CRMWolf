"""Durable continuation identity for the pending-task LangGraph.

A continuation reference is both a storage locator and a tenant-scoped
capability.  Callers must never trust its identity fields independently from
its thread id; this module constructs and validates the pair as one value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict
from uuid import uuid4

from app.services.agent.types import coerce_json_dict

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

PENDING_TASK_RUNTIME = "crm_agent_pending_task"
PENDING_TASK_CHILD_NAMESPACE_PREFIX = "pending_task_subgraph:"


class PendingTaskContinuationRef(TypedDict):
    """Checkpoint-safe identity of one pending-task invocation/continuation."""

    runtime: str
    continuation_id: NotRequired[str]
    thread_id: str
    checkpoint_ns: NotRequired[str]
    team_id: int
    user_id: int
    session_id: int
    task_id: int | None


def new_pending_task_continuation(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None,
    continuation_id: str | None = None,
) -> PendingTaskContinuationRef:
    """Create an isolated continuation for one new pending-task invocation."""

    resolved_continuation_id = continuation_id or uuid4().hex
    return {
        "runtime": PENDING_TASK_RUNTIME,
        "continuation_id": resolved_continuation_id,
        "thread_id": pending_task_thread_id(
            team_id=team_id,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            continuation_id=resolved_continuation_id,
        ),
        "checkpoint_ns": "",
        "team_id": team_id,
        "user_id": user_id,
        "session_id": session_id,
        "task_id": task_id,
    }


def pending_task_thread_id(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    task_id: int | None,
    continuation_id: str | None = None,
) -> str:
    """Return the canonical storage thread for a continuation.

    References created before invocation isolation was introduced have no
    continuation id.  Their canonical legacy thread remains readable solely
    for durable resume compatibility.
    """

    task_key = str(task_id) if task_id is not None else "session"
    base = f"crm_agent_pending:{team_id}:{user_id}:{session_id}:{task_key}"
    return f"{base}:{continuation_id}" if continuation_id else base


def pending_task_continuation_from_json(
    value: object,
    *,
    expected_team_id: int | None = None,
    expected_user_id: int | None = None,
    expected_session_id: int | None = None,
) -> PendingTaskContinuationRef | None:
    """Parse and authenticate a continuation reference.

    The canonical thread is derived again from the scoped identity.  A payload
    whose declared tenant/session does not own its storage locator is rejected.
    """

    payload = coerce_json_dict(value)
    if payload.get("runtime") != PENDING_TASK_RUNTIME:
        return None
    team_id = _integer(payload.get("team_id"))
    user_id = _integer(payload.get("user_id"))
    session_id = _integer(payload.get("session_id"))
    if team_id is None or user_id is None or session_id is None:
        return None
    if expected_team_id is not None and team_id != expected_team_id:
        return None
    if expected_user_id is not None and user_id != expected_user_id:
        return None
    if expected_session_id is not None and session_id != expected_session_id:
        return None

    task_value = payload.get("task_id")
    task_id = _integer(task_value) if task_value is not None else None
    if task_value is not None and task_id is None:
        return None
    continuation_value = payload.get("continuation_id")
    continuation_id = continuation_value if isinstance(continuation_value, str) and continuation_value else None
    thread_id = payload.get("thread_id")
    if not isinstance(thread_id, str) or thread_id != pending_task_thread_id(
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        continuation_id=continuation_id,
    ):
        return None
    checkpoint_ns = payload.get("checkpoint_ns")
    if checkpoint_ns is not None and not isinstance(checkpoint_ns, str):
        return None
    if (
        isinstance(checkpoint_ns, str)
        and checkpoint_ns
        and not checkpoint_ns.startswith(PENDING_TASK_CHILD_NAMESPACE_PREFIX)
    ):
        return None

    result: PendingTaskContinuationRef = {
        "runtime": PENDING_TASK_RUNTIME,
        "thread_id": thread_id,
        "checkpoint_ns": checkpoint_ns if isinstance(checkpoint_ns, str) else "",
        "team_id": team_id,
        "user_id": user_id,
        "session_id": session_id,
        "task_id": task_id,
    }
    if continuation_id:
        result["continuation_id"] = continuation_id
    return result


def bind_pending_task_namespace(
    continuation: PendingTaskContinuationRef,
    checkpoint_ns: str,
) -> PendingTaskContinuationRef:
    """Return the same continuation bound to LangGraph's dynamic child namespace."""

    if checkpoint_ns and not checkpoint_ns.startswith(PENDING_TASK_CHILD_NAMESPACE_PREFIX):
        raise ValueError("invalid pending-task checkpoint namespace")
    return {**continuation, "checkpoint_ns": checkpoint_ns}


def pending_task_checkpoint_config(
    continuation: PendingTaskContinuationRef,
    *,
    include_namespace: bool = True,
) -> RunnableConfig:
    """Project a validated continuation to LangGraph checkpoint configuration."""

    configurable: dict[str, object] = {"thread_id": continuation["thread_id"]}
    checkpoint_ns = continuation.get("checkpoint_ns")
    if include_namespace and checkpoint_ns:
        configurable["checkpoint_ns"] = checkpoint_ns
    return {
        "configurable": configurable,
        "metadata": {
            "team_id": continuation["team_id"],
            "user_id": continuation["user_id"],
            "session_id": continuation["session_id"],
            "task_id": continuation["task_id"],
            "runtime": PENDING_TASK_RUNTIME,
            "runtime_namespace": PENDING_TASK_RUNTIME,
            "continuation_id": continuation.get("continuation_id"),
        },
    }


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
