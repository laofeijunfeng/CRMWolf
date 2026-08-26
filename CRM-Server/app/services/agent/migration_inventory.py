"""Content-free inventory for the CRM Agent single-version checkpoint cutover.

The inventory deliberately reuses the exact checkpoint ownership matrix used by
``AgentCheckpointCutoverService``.  A release report therefore cannot become
"green" by classifying data differently from the destructive cutover.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime  # noqa: TC003 - Pydantic resolves this annotation at runtime.
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, text

from app.models.agent import AgentSessionStatus
from app.services.agent.checkpoint_cutover import (
    LEGACY_ACTIVE_TASK_STATUSES,
    AgentCheckpointCutoverError,
    AgentCheckpointMatrixReader,
    CheckpointCategory,
    classify_checkpoint_identity,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.engine import Connection

    from app.services.agent.checkpoint_cutover import CheckpointMatrixSnapshot

CHECKPOINT_CATEGORY_ORDER: Final[tuple[CheckpointCategory, ...]] = (
    "target_root",
    "target_workflow",
    "legacy_root",
    "legacy_query",
    "legacy_workflow",
    "legacy_pending_confirmed",
    "legacy_helper",
    "customer_intelligence",
    "adjacent_workflow",
    "unknown",
)

KNOWN_MESSAGE_PAYLOAD_KEY_SETS: Final[frozenset[frozenset[str]]] = frozenset(
    {
        frozenset({"source"}),
        frozenset({"source", "trace_events"}),
        frozenset({"source", "trace_events", "content_format"}),
        frozenset({"source", "content_format"}),
        frozenset({"source", "for_user_message_id", "trace_events", "content_format"}),
        frozenset(
            {
                "source",
                "for_user_message_id",
                "trace_events",
                "content_format",
                "turn_observability",
            }
        ),
        frozenset(
            {
                "source",
                "recovered_for_user_message_id",
                "trace_events",
                "content_format",
            }
        ),
        frozenset(
            {
                "source",
                "recovered_for_user_message_id",
                "trace_events",
                "content_format",
                "reason",
                "recovery_status",
            }
        ),
        frozenset(
            {
                "source",
                "recovered_for_user_message_id",
                "trace_events",
                "content_format",
                "reason",
                "recovery_status",
                "related_task_id",
            }
        ),
        frozenset(
            {
                "source",
                "recovered_for_user_message_id",
                "trace_events",
                "content_format",
                "reason",
                "recovery_status",
                "activity_id",
                "task_id",
            }
        ),
    }
)
_KNOWN_MESSAGE_ROLES: Final[frozenset[str]] = frozenset({"USER", "ASSISTANT"})
_KNOWN_MESSAGE_EVENT_TYPES: Final[frozenset[str]] = frozenset({"user_message", "assistant_message"})
_KNOWN_SESSION_STATUSES: Final[frozenset[str]] = frozenset(
    {
        AgentSessionStatus.ACTIVE,
        AgentSessionStatus.COMPLETED,
        AgentSessionStatus.ARCHIVED,
        AgentSessionStatus.FAILED,
    }
)
_KNOWN_TASK_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "PENDING",
        "WAITING_USER",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "SUSPENDED",
    }
)
_REQUIRED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "crm_agent_sessions",
        "crm_agent_tasks",
        "crm_agent_messages",
        "crm_langgraph_checkpoints",
        "crm_langgraph_checkpoint_blobs",
        "crm_langgraph_checkpoint_writes",
    }
)


class MessageInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    total: int = Field(default=0, ge=0)
    roles: dict[str, int] = Field(default_factory=dict)
    event_types: dict[str, int] = Field(default_factory=dict)
    payload_shapes: dict[str, int] = Field(default_factory=dict)
    invalid_payload_count: int = Field(default=0, ge=0)
    unknown_payload_shape_count: int = Field(default=0, ge=0)
    unknown_role_count: int = Field(default=0, ge=0)
    unknown_event_type_count: int = Field(default=0, ge=0)


class CheckpointCategoryInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    checkpoint_row_count: int = Field(default=0, ge=0)
    latest_checkpoint_count: int = Field(default=0, ge=0)


class CheckpointInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    total_rows: int = Field(default=0, ge=0)
    latest_checkpoint_count: int = Field(default=0, ge=0)
    categories: dict[CheckpointCategory, CheckpointCategoryInventory]


class ActiveStateInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    session_statuses: dict[str, int] = Field(default_factory=dict)
    task_statuses: dict[str, int] = Field(default_factory=dict)
    active_legacy_task_count: int = Field(default=0, ge=0)
    unknown_session_status_count: int = Field(default=0, ge=0)
    unknown_task_status_count: int = Field(default=0, ge=0)


class AgentMigrationInventoryReport(BaseModel):
    """Safe-to-share release evidence without user content or entity identifiers."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["crm.agent.migration-inventory.v2"] = "crm.agent.migration-inventory.v2"
    as_of: datetime
    messages: MessageInventory
    checkpoints: CheckpointInventory
    active_state: ActiveStateInventory
    blocking_unknowns: list[str] = Field(default_factory=list)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AgentMigrationInventory:
    """Collect one reproducible inventory through the destructive cutover seam."""

    def __init__(self, engine: Engine, *, as_of: datetime) -> None:
        self._engine = engine
        self._as_of = as_of

    def collect(self) -> AgentMigrationInventoryReport:
        table_names = set(inspect(self._engine).get_table_names())
        missing = sorted(_REQUIRED_TABLES - table_names)
        if missing:
            raise RuntimeError(f"migration inventory requires tables: {', '.join(missing)}")

        messages = self._collect_messages()
        active_state = self._collect_active_state()
        with self._engine.connect() as connection:
            try:
                snapshot = AgentCheckpointMatrixReader(connection).snapshot(as_of=self._as_of)
            except AgentCheckpointCutoverError as error:
                checkpoints = self._collect_raw_checkpoint_counts(connection)
                matrix_blockers = list(error.blockers)
            else:
                checkpoints = self._checkpoint_inventory(snapshot)
                matrix_blockers = list(snapshot.blockers)

        blockers = set(matrix_blockers)
        if messages.invalid_payload_count:
            blockers.add("message_payload:invalid_json_shape")
        if messages.unknown_payload_shape_count:
            blockers.add("message_payload:unknown_shape")
        if messages.unknown_role_count:
            blockers.add("message_role:unknown")
        if messages.unknown_event_type_count:
            blockers.add("message_event_type:unknown")
        if active_state.unknown_session_status_count:
            blockers.add("session_status:unknown")
        if active_state.unknown_task_status_count:
            blockers.add("task_status:unknown")

        report_data = {
            "schema_version": "crm.agent.migration-inventory.v2",
            "as_of": self._as_of.isoformat(),
            "messages": messages.model_dump(mode="json"),
            "checkpoints": checkpoints.model_dump(mode="json"),
            "active_state": active_state.model_dump(mode="json"),
            "blocking_unknowns": sorted(blockers),
        }
        return AgentMigrationInventoryReport(
            as_of=self._as_of,
            messages=messages,
            checkpoints=checkpoints,
            active_state=active_state,
            blocking_unknowns=sorted(blockers),
            evidence_sha256=_sha256(report_data),
        )

    def _collect_messages(self) -> MessageInventory:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("SELECT role, event_type, payload_json FROM crm_agent_messages ORDER BY id")
            ).all()

        roles: Counter[str] = Counter()
        event_types: Counter[str] = Counter()
        payload_shapes: Counter[str] = Counter()
        invalid_payload_count = 0
        unknown_payload_shape_count = 0
        unknown_role_count = 0
        unknown_event_type_count = 0
        for row in rows:
            role = str(row.role)
            if role in _KNOWN_MESSAGE_ROLES:
                roles[role] += 1
            else:
                roles["<unrecognized>"] += 1
                unknown_role_count += 1

            event_type = "null" if row.event_type is None else str(row.event_type)
            if event_type == "null" or event_type in _KNOWN_MESSAGE_EVENT_TYPES:
                event_types[event_type] += 1
            else:
                event_types["<unrecognized>"] += 1
                unknown_event_type_count += 1

            payload, valid = coerce_agent_message_payload(row.payload_json)
            if payload is None and valid:
                payload_shapes["null"] += 1
            elif isinstance(payload, dict) and valid:
                keys = frozenset(str(key) for key in payload)
                if keys in KNOWN_MESSAGE_PAYLOAD_KEY_SETS:
                    payload_shapes[",".join(sorted(keys))] += 1
                else:
                    payload_shapes[f"unknown_object:{len(keys)}_keys"] += 1
                    unknown_payload_shape_count += 1
            else:
                payload_shapes[f"invalid:{type(payload).__name__}"] += 1
                invalid_payload_count += 1

        return MessageInventory(
            total=len(rows),
            roles=dict(sorted(roles.items())),
            event_types=dict(sorted(event_types.items())),
            payload_shapes=dict(sorted(payload_shapes.items())),
            invalid_payload_count=invalid_payload_count,
            unknown_payload_shape_count=unknown_payload_shape_count,
            unknown_role_count=unknown_role_count,
            unknown_event_type_count=unknown_event_type_count,
        )

    def _collect_active_state(self) -> ActiveStateInventory:
        with self._engine.connect() as connection:
            session_rows = connection.execute(
                text("SELECT status, COUNT(*) AS row_count FROM crm_agent_sessions GROUP BY status")
            ).all()
            task_rows = connection.execute(
                text("SELECT status, COUNT(*) AS row_count FROM crm_agent_tasks GROUP BY status")
            ).all()

        session_statuses = {str(row.status): int(row.row_count) for row in session_rows}
        task_statuses = {str(row.status): int(row.row_count) for row in task_rows}
        return ActiveStateInventory(
            session_statuses=dict(sorted(session_statuses.items())),
            task_statuses=dict(sorted(task_statuses.items())),
            active_legacy_task_count=sum(
                count for status, count in task_statuses.items() if status in LEGACY_ACTIVE_TASK_STATUSES
            ),
            unknown_session_status_count=sum(
                count for status, count in session_statuses.items() if status not in _KNOWN_SESSION_STATUSES
            ),
            unknown_task_status_count=sum(
                count for status, count in task_statuses.items() if status not in _KNOWN_TASK_STATUSES
            ),
        )

    @staticmethod
    def _checkpoint_inventory(snapshot: CheckpointMatrixSnapshot) -> CheckpointInventory:
        latest_counts: Counter[CheckpointCategory] = Counter()
        for identity in snapshot.identities:
            if (
                snapshot.latest_checkpoint_ids.get((identity.thread_id, identity.checkpoint_ns))
                == identity.checkpoint_id
            ):
                latest_counts[identity.category] += 1
        categories = {
            category: CheckpointCategoryInventory(
                checkpoint_row_count=snapshot.category_checkpoint_counts[category],
                latest_checkpoint_count=latest_counts[category],
            )
            for category in CHECKPOINT_CATEGORY_ORDER
        }
        return CheckpointInventory(
            total_rows=len(snapshot.identities),
            latest_checkpoint_count=len(snapshot.latest_checkpoint_ids),
            categories=categories,
        )

    @staticmethod
    def _collect_raw_checkpoint_counts(connection: Connection) -> CheckpointInventory:
        rows = connection.execute(
            text(
                """SELECT thread_id, checkpoint_ns, checkpoint_id
                   FROM crm_langgraph_checkpoints
                   ORDER BY thread_id, checkpoint_ns, checkpoint_id"""
            )
        ).all()
        counts: Counter[CheckpointCategory] = Counter()
        latest: dict[tuple[str, str], tuple[str, CheckpointCategory]] = {}
        for row in rows:
            thread_id = str(row.thread_id)
            checkpoint_ns = str(row.checkpoint_ns or "")
            category = classify_checkpoint_identity(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
            )
            counts[category] += 1
            latest[(thread_id, checkpoint_ns)] = (str(row.checkpoint_id), category)
        latest_counts: Counter[CheckpointCategory] = Counter(category for _, category in latest.values())
        return CheckpointInventory(
            total_rows=len(rows),
            latest_checkpoint_count=len(latest),
            categories={
                category: CheckpointCategoryInventory(
                    checkpoint_row_count=counts[category],
                    latest_checkpoint_count=latest_counts[category],
                )
                for category in CHECKPOINT_CATEGORY_ORDER
            },
        )


def coerce_agent_message_payload(value: object) -> tuple[object, bool]:
    """Normalize a SQL JSON value without accepting non-object payload contracts."""

    if value is None or isinstance(value, dict):
        return value, True
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value, False
        return decoded, decoded is None or isinstance(decoded, dict)
    return value, False


def _sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
