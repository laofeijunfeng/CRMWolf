"""Root-owned durable continuation identity for the pending-task LangGraph.

Pending-task interrupts are nested work owned by the Agent Root Graph. A
continuation is therefore valid only when it points at the exact root thread
and dynamic child namespace that LangGraph assigned to that invocation.
"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Literal, TypedDict

from app.services.agent.types import coerce_json_dict

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

PENDING_TASK_RUNTIME = "crm_agent_pending_task"
PENDING_TASK_CONTINUATION_SCHEMA_VERSION = 2
PENDING_TASK_CHILD_NAMESPACE_PREFIX = "pending_task_subgraph:"


class PendingTaskContinuationRef(TypedDict):
    """Authenticated locator for one root-owned pending-task invocation."""

    schema_version: Literal[2]
    runtime: Literal["crm_agent_pending_task"]
    continuation_id: str
    persistence_scope: Literal["root"]
    thread_id: str
    checkpoint_ns: str
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
    root_thread_id: str,
    checkpoint_ns: str,
) -> PendingTaskContinuationRef:
    """Create the only supported V2 continuation: root thread + exact child ns."""

    expected_prefix = _root_thread_prefix(
        team_id=team_id,
        user_id=user_id,
        session_id=session_id,
    )
    if not root_thread_id.startswith(expected_prefix):
        raise ValueError("invalid pending-task root thread")
    if not checkpoint_ns.startswith(PENDING_TASK_CHILD_NAMESPACE_PREFIX):
        raise ValueError("invalid pending-task checkpoint namespace")
    continuation_id = _root_continuation_id(
        root_thread_id=root_thread_id,
        checkpoint_ns=checkpoint_ns,
        task_id=task_id,
    )
    return {
        "schema_version": PENDING_TASK_CONTINUATION_SCHEMA_VERSION,
        "runtime": PENDING_TASK_RUNTIME,
        "continuation_id": continuation_id,
        "persistence_scope": "root",
        "thread_id": root_thread_id,
        "checkpoint_ns": checkpoint_ns,
        "team_id": team_id,
        "user_id": user_id,
        "session_id": session_id,
        "task_id": task_id,
    }


def build_agent_root_thread_id(
    *,
    team_id: int,
    user_id: int,
    session_id: int,
    session_key: str | None = None,
) -> str:
    key = session_key or str(session_id)
    return f"{_root_thread_prefix(team_id=team_id, user_id=user_id, session_id=session_id)}{key}"


def pending_task_continuation_from_json(
    value: object,
    *,
    expected_team_id: int | None = None,
    expected_user_id: int | None = None,
    expected_session_id: int | None = None,
    expected_thread_id: str | None = None,
) -> PendingTaskContinuationRef | None:
    """Parse and authenticate a V2 continuation against its owning root graph."""

    continuation = pending_task_continuation_shape_from_json(value)
    if continuation is None or expected_thread_id is None:
        return None
    if expected_team_id is not None and continuation["team_id"] != expected_team_id:
        return None
    if expected_user_id is not None and continuation["user_id"] != expected_user_id:
        return None
    if expected_session_id is not None and continuation["session_id"] != expected_session_id:
        return None
    if continuation["thread_id"] != expected_thread_id:
        return None
    return continuation


def pending_task_continuation_shape_from_json(value: object) -> PendingTaskContinuationRef | None:
    """Preserve only structurally valid V2 root-owned locators during JSON decode."""

    payload = coerce_json_dict(value)
    if payload.get("schema_version") != PENDING_TASK_CONTINUATION_SCHEMA_VERSION:
        return None
    if payload.get("runtime") != PENDING_TASK_RUNTIME or payload.get("persistence_scope") != "root":
        return None
    team_id = _integer(payload.get("team_id"))
    user_id = _integer(payload.get("user_id"))
    session_id = _integer(payload.get("session_id"))
    if team_id is None or user_id is None or session_id is None:
        return None
    task_value = payload.get("task_id")
    task_id = _integer(task_value) if task_value is not None else None
    if task_value is not None and task_id is None:
        return None
    thread_id = payload.get("thread_id")
    checkpoint_ns = payload.get("checkpoint_ns")
    continuation_id = payload.get("continuation_id")
    if not isinstance(thread_id, str) or not thread_id.startswith(
        _root_thread_prefix(team_id=team_id, user_id=user_id, session_id=session_id)
    ):
        return None
    if not isinstance(checkpoint_ns, str) or not checkpoint_ns.startswith(PENDING_TASK_CHILD_NAMESPACE_PREFIX):
        return None
    if not isinstance(continuation_id, str) or continuation_id != _root_continuation_id(
        root_thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
        task_id=task_id,
    ):
        return None
    return {
        "schema_version": PENDING_TASK_CONTINUATION_SCHEMA_VERSION,
        "runtime": PENDING_TASK_RUNTIME,
        "continuation_id": continuation_id,
        "persistence_scope": "root",
        "thread_id": thread_id,
        "checkpoint_ns": checkpoint_ns,
        "team_id": team_id,
        "user_id": user_id,
        "session_id": session_id,
        "task_id": task_id,
    }


def pending_task_checkpoint_config(continuation: PendingTaskContinuationRef) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": continuation["thread_id"],
            "checkpoint_ns": continuation["checkpoint_ns"],
        },
        "metadata": {
            "team_id": continuation["team_id"],
            "user_id": continuation["user_id"],
            "session_id": continuation["session_id"],
            "task_id": continuation["task_id"],
            "runtime": PENDING_TASK_RUNTIME,
            "runtime_namespace": PENDING_TASK_RUNTIME,
            "continuation_id": continuation["continuation_id"],
            "continuation_schema_version": PENDING_TASK_CONTINUATION_SCHEMA_VERSION,
        },
    }


def _root_thread_prefix(*, team_id: int, user_id: int, session_id: int) -> str:
    return f"crm_agent:{team_id}:{user_id}:{session_id}:"


def _root_continuation_id(*, root_thread_id: str, checkpoint_ns: str, task_id: int | None) -> str:
    identity = f"v2|{root_thread_id}|{checkpoint_ns}|{task_id}"
    return sha256(identity.encode("utf-8")).hexdigest()[:32]


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
