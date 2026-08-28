"""Single-version checkpoint cutover for the thin Root and native Workflow runtime.

This module is an offline release tool. It never runs in the Agent request path and
it deliberately has one public operation: validate the whole checkpoint ownership
matrix, delete quiescent legacy Agent-owned rows, and journal the resulting state.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final, Literal

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import inspect, text

from app.services.agent.checkpoint_serde_inspection import CheckpointSerdeInspector
from app.services.agent.orchestrator.contracts import WorkflowContinuation

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Row

CheckpointCategory = Literal[
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
]

TARGET_ROOT_STATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "turn",
        "context_snapshot",
        "decision",
        "query_input",
        "resolved_action",
        "workflow_input",
        "workflow_result",
        "dispatch_result",
        "pending_case_public_id",
    }
)
TARGET_WORKFLOW_STATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "workflow_input",
        "workflow_id",
        "workflow_plan",
        "workflow_interaction",
        "workflow_resume",
        "workflow_result",
    }
)
LEGACY_ACTIVE_TASK_STATUSES: Final[frozenset[str]] = frozenset({"PENDING", "WAITING_USER", "RUNNING", "SUSPENDED"})
LEGACY_HELPER_THREAD_FAMILIES: Final[frozenset[str]] = frozenset(
    {
        "crm_agent_action_planning",
        "crm_agent_action_review",
        "crm_agent_business_context",
        "crm_agent_contact",
        "crm_agent_creation_duplicates",
        "crm_agent_customer_activity",
        "crm_agent_customer_creation",
        "crm_agent_customer_member",
        "crm_agent_customer_resolution",
        "crm_agent_deployment_info",
        "crm_agent_follow_up_confirmation",
        "crm_agent_follow_up_quality",
        "crm_agent_invoice_title",
        "crm_agent_lead",
        "crm_agent_opportunity",
        "crm_agent_payment_record",
        "crm_agent_pending_interaction",
        "crm_agent_pending_preflight",
        "crm_agent_procurement_application",
        "crm_agent_procurement_method",
        "crm_agent_resource_resolution",
        "crm_agent_work_summary",
    }
)
ADJACENT_WORKFLOW_THREAD_FAMILIES: Final[frozenset[str]] = frozenset(
    {"customer_activity", "customer_activity_post_commit", "confirmation_delivery"}
)
LEGACY_AGENT_CATEGORIES: Final[frozenset[CheckpointCategory]] = frozenset(
    {
        "legacy_root",
        "legacy_query",
        "legacy_workflow",
        "legacy_pending_confirmed",
        "legacy_helper",
    }
)
CUTOVER_JOURNAL_KEY: Final = "agent-checkpoint-cutover-v2"
CUTOVER_SCHEMA_VERSION: Final = "crm.agent.checkpoint-cutover.v2"


class AgentCheckpointCutoverError(RuntimeError):
    """The checkpoint database cannot be cut over without losing ownership."""

    def __init__(self, blockers: str | list[str] | set[str]) -> None:
        normalized = [blockers] if isinstance(blockers, str) else sorted(set(blockers))
        self.blockers = normalized
        super().__init__(", ".join(normalized))


class AgentCheckpointCutoverResult(BaseModel):
    """Content-free evidence for one committed checkpoint cutover."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["crm.agent.checkpoint-cutover.v2"] = CUTOVER_SCHEMA_VERSION
    already_completed: bool
    deleted_legacy_checkpoint_count: int = Field(ge=0)
    deleted_legacy_blob_count: int = Field(ge=0)
    deleted_legacy_write_count: int = Field(ge=0)
    target_root_checkpoint_count: int = Field(ge=0)
    target_workflow_checkpoint_count: int = Field(ge=0)
    retained_customer_intelligence_checkpoint_count: int = Field(ge=0)
    retained_adjacent_workflow_checkpoint_count: int = Field(ge=0)
    retained_rows_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CheckpointIdentity:
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
    parent_checkpoint_id: str | None
    checkpoint_type: str
    checkpoint_blob: bytes
    metadata_type: str
    metadata_blob: bytes
    category: CheckpointCategory
    runtime: str
    runtime_namespace: str
    state_keys: frozenset[str]
    pending_sends: bool


@dataclass(frozen=True)
class CheckpointMatrixSnapshot:
    identities: tuple[CheckpointIdentity, ...]
    latest_checkpoint_ids: dict[tuple[str, str], str]
    category_checkpoint_counts: Counter[CheckpointCategory]
    blockers: tuple[str, ...]

    @property
    def legacy_threads(self) -> frozenset[str]:
        return frozenset(
            identity.thread_id for identity in self.identities if identity.category in LEGACY_AGENT_CATEGORIES
        )


_STRICT_SERDE = JsonPlusSerializer(allowed_msgpack_modules=None)


def checkpoint_namespace_shape(checkpoint_ns: str) -> str:
    """Redact dynamic LangGraph namespace identities while retaining topology."""

    if not checkpoint_ns:
        return "<root>"
    parts: list[str] = []
    for segment in checkpoint_ns.split("|"):
        name, separator, _identity = segment.partition(":")
        parts.append(f"{name}:*" if separator else segment)
    return "|".join(parts)


def parse_target_root_thread(thread_id: str) -> tuple[int, int, int] | None:
    parts = thread_id.split(":")
    if len(parts) != 4 or parts[0] != "crm_agent":
        return None
    try:
        team_id, user_id, session_id = (int(part) for part in parts[1:])
    except ValueError:
        return None
    if min(team_id, user_id, session_id) <= 0:
        return None
    return team_id, user_id, session_id


def parse_turn_root_thread(thread_id: str) -> tuple[int, int, int, str] | None:
    """Parse the canonical per-turn Root checkpoint identity."""

    parts = thread_id.split(":")
    if len(parts) != 5 or parts[0] != "crm_agent_turn" or not parts[4]:
        return None
    try:
        team_id, user_id, session_id = (int(part) for part in parts[1:4])
    except ValueError:
        return None
    turn_token = parts[4]
    if min(team_id, user_id, session_id) <= 0 or len(turn_token) != 32:
        return None
    try:
        int(turn_token, 16)
    except ValueError:
        return None
    return team_id, user_id, session_id, turn_token


def parse_legacy_root_thread(thread_id: str) -> tuple[int, int, int, str] | None:
    parts = thread_id.split(":")
    if len(parts) != 5 or parts[0] != "crm_agent" or not parts[4]:
        return None
    try:
        team_id, user_id, session_id = (int(part) for part in parts[1:4])
    except ValueError:
        return None
    if min(team_id, user_id, session_id) <= 0:
        return None
    return team_id, user_id, session_id, parts[4]


def classify_checkpoint_identity(*, thread_id: str, checkpoint_ns: str) -> CheckpointCategory:
    """Classify a physical identity against the v2 single-version matrix."""

    family = thread_id.partition(":")[0]
    namespace_shape = checkpoint_namespace_shape(checkpoint_ns)
    if parse_turn_root_thread(thread_id) is not None or parse_target_root_thread(thread_id) is not None:
        if namespace_shape == "<root>":
            return "target_root"
        if namespace_shape.startswith("workflow_subgraph:"):
            return "target_workflow"
        return "unknown"
    if parse_legacy_root_thread(thread_id) is not None:
        if namespace_shape in {"<root>", "crm_agent"}:
            return "legacy_root"
        if namespace_shape.startswith("query_agent:"):
            return "legacy_query"
        if namespace_shape.startswith("workflow_graph:") or namespace_shape.startswith(
            ("reconcile_pending_business_interactions:", "resolve_follow_up_confirmation:")
        ):
            return "legacy_workflow"
        if namespace_shape.startswith(("pending_task_subgraph:", "confirmed_task_execution:")):
            return "legacy_pending_confirmed"
        return "unknown"
    if family == "crm_agent_new_flow":
        return "legacy_workflow"
    if family in {"crm_agent_pending", "crm_agent_confirmed"}:
        return "legacy_pending_confirmed"
    if family in LEGACY_HELPER_THREAD_FAMILIES:
        return "legacy_helper"
    if family == "crm_agent_customer_intelligence":
        return "customer_intelligence"
    if family in ADJACENT_WORKFLOW_THREAD_FAMILIES:
        return "adjacent_workflow"
    return "unknown"


def is_agent_legacy_category(category: CheckpointCategory) -> bool:
    return category in LEGACY_AGENT_CATEGORIES


def _loads(serializer: JsonPlusSerializer, serde_type: object, blob: object, *, blocker: str) -> object:
    if not isinstance(serde_type, str) or not isinstance(blob, (bytes, bytearray, memoryview)):
        raise AgentCheckpointCutoverError(blocker)
    try:
        return serializer.loads_typed((serde_type, bytes(blob)))
    except Exception as error:
        raise AgentCheckpointCutoverError(blocker) from error


def _loads_without_custom_constructors(
    serde_type: object,
    blob: object,
    *,
    blocker: str,
) -> object:
    inspector = CheckpointSerdeInspector()
    _loads(inspector, serde_type, blob, blocker=blocker)
    if inspector.custom_type_occurrences:
        raise AgentCheckpointCutoverError(blocker)
    return _loads(_STRICT_SERDE, serde_type, blob, blocker=blocker)


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): nested for key, nested in value.items()}
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return {str(key): nested for key, nested in decoded.items()}
    return {}


def _business_state_keys(checkpoint: dict[str, object]) -> frozenset[str]:
    versions = checkpoint.get("channel_versions")
    if not isinstance(versions, dict):
        raise AgentCheckpointCutoverError("checkpoint:invalid_channel_versions")
    return frozenset(str(channel) for channel in versions if not str(channel).startswith(("__", "branch:", "join:")))


def _runtime_metadata(metadata: dict[str, object]) -> tuple[str, str]:
    runtime = metadata.get("runtime")
    runtime_namespace = metadata.get("runtime_namespace")
    return (
        str(runtime) if isinstance(runtime, str) and runtime else "<missing>",
        str(runtime_namespace) if isinstance(runtime_namespace, str) and runtime_namespace else "<missing>",
    )


def _metadata_matches_category(identity: CheckpointIdentity) -> bool:
    if identity.category == "target_root":
        return identity.runtime == "crm_agent_root" and identity.runtime_namespace == "crm_agent"
    if identity.category == "target_workflow":
        return identity.runtime == "crm_agent_root" and identity.runtime_namespace == "crm_agent"
    if identity.category == "legacy_root":
        return identity.runtime in {"crm_agent", "crm_agent_root"}
    if identity.category == "legacy_query":
        return identity.runtime in {"crm_agent", "crm_agent_root"}
    if identity.category == "legacy_workflow":
        family = identity.thread_id.partition(":")[0]
        if family == "crm_agent_new_flow":
            return identity.runtime == "crm_agent_new_flow"
        return identity.runtime in {
            "crm_agent",
            "crm_agent_root",
            "crm_agent_workflow",
            "crm_agent_customer_resolution",
            "crm_agent_action_planning",
            "crm_agent_action_review",
            "crm_agent_business_context",
            "crm_agent_customer_activity",
            "crm_agent_follow_up_quality",
        }
    if identity.category == "legacy_pending_confirmed":
        return identity.runtime in {"crm_agent_pending_task", "crm_agent_confirmed_task"}
    if identity.category == "legacy_helper":
        return identity.runtime == identity.thread_id.partition(":")[0]
    if identity.category == "customer_intelligence":
        return identity.runtime == "crm_agent_customer_intelligence"
    return identity.category == "adjacent_workflow"


def _hash_value(hasher: hashlib._Hash, value: object) -> None:
    if value is None:
        payload = b"<null>"
    elif isinstance(value, bytes):
        payload = value
    elif isinstance(value, (bytearray, memoryview)):
        payload = bytes(value)
    elif isinstance(value, datetime):
        payload = value.isoformat(timespec="microseconds").encode()
    else:
        payload = str(value).encode("utf-8")
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


class AgentCheckpointMatrixReader:
    """Read and validate checkpoint identities through one content-free seam."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._inspection_serde = CheckpointSerdeInspector()

    def snapshot(self, *, as_of: datetime) -> CheckpointMatrixSnapshot:
        rows = self._connection.execute(
            text(
                """SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                          checkpoint_type, checkpoint_blob, metadata_type, metadata_blob
                   FROM crm_langgraph_checkpoints
                   ORDER BY thread_id, checkpoint_ns, checkpoint_id"""
            )
        ).all()
        latest: dict[tuple[str, str], str] = {}
        for row in rows:
            latest[(str(row.thread_id), str(row.checkpoint_ns or ""))] = str(row.checkpoint_id)

        identities: list[CheckpointIdentity] = []
        blockers: set[str] = set()
        counts: Counter[CheckpointCategory] = Counter()
        for row in rows:
            thread_id = str(row.thread_id)
            checkpoint_ns = str(row.checkpoint_ns or "")
            category = classify_checkpoint_identity(thread_id=thread_id, checkpoint_ns=checkpoint_ns)
            counts[category] += 1
            if category in {"target_root", "target_workflow"}:
                blocker = f"{category}:custom_serde"
                checkpoint = _loads_without_custom_constructors(
                    row.checkpoint_type,
                    row.checkpoint_blob,
                    blocker=blocker,
                )
                metadata = _loads_without_custom_constructors(
                    row.metadata_type,
                    row.metadata_blob,
                    blocker=blocker,
                )
            else:
                checkpoint = _loads(
                    self._inspection_serde,
                    row.checkpoint_type,
                    row.checkpoint_blob,
                    blocker="checkpoint:unreadable",
                )
                metadata = _loads(
                    self._inspection_serde,
                    row.metadata_type,
                    row.metadata_blob,
                    blocker="checkpoint:unreadable",
                )
            if not isinstance(checkpoint, dict) or not isinstance(metadata, dict):
                blockers.add("checkpoint:invalid_payload")
                continue
            runtime, runtime_namespace = _runtime_metadata(metadata)
            try:
                state_keys = _business_state_keys(checkpoint)
            except AgentCheckpointCutoverError as error:
                blockers.update(error.blockers)
                state_keys = frozenset()
            identity = CheckpointIdentity(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=str(row.checkpoint_id),
                parent_checkpoint_id=(str(row.parent_checkpoint_id) if row.parent_checkpoint_id is not None else None),
                checkpoint_type=str(row.checkpoint_type),
                checkpoint_blob=bytes(row.checkpoint_blob),
                metadata_type=str(row.metadata_type),
                metadata_blob=bytes(row.metadata_blob),
                category=category,
                runtime=runtime,
                runtime_namespace=runtime_namespace,
                state_keys=state_keys,
                pending_sends=bool(checkpoint.get("pending_sends")),
            )
            identities.append(identity)
            if category == "unknown":
                blockers.add("checkpoint_category:unknown")
            elif not _metadata_matches_category(identity):
                blockers.add(f"{category}:metadata")
            if category == "target_root" and not state_keys <= TARGET_ROOT_STATE_KEYS:
                blockers.add("target_root:unknown_state")
            if category == "target_workflow" and not state_keys <= TARGET_WORKFLOW_STATE_KEYS:
                blockers.add("target_workflow:unknown_state")

        self._validate_session_ownership(identities, blockers)
        self._validate_target_physical_payloads(identities, blockers)
        self._validate_latest_legacy_activity(identities, latest, blockers)
        self._validate_target_workflow_continuations(identities, latest, blockers, as_of=as_of)
        self._validate_customer_intelligence_physical_integrity(identities, latest, blockers)
        self._validate_customer_intelligence_ownership(identities, latest, blockers, as_of=as_of)
        self._validate_active_legacy_tasks(blockers)
        return CheckpointMatrixSnapshot(
            identities=tuple(identities),
            latest_checkpoint_ids=latest,
            category_checkpoint_counts=counts,
            blockers=tuple(sorted(blockers)),
        )

    def _validate_target_physical_payloads(
        self,
        identities: list[CheckpointIdentity],
        blockers: set[str],
    ) -> None:
        for identity in identities:
            if identity.category not in {"target_root", "target_workflow"}:
                continue
            blocker = f"{identity.category}:custom_serde"
            checkpoint = _loads_without_custom_constructors(
                identity.checkpoint_type,
                identity.checkpoint_blob,
                blocker=blocker,
            )
            if not isinstance(checkpoint, dict) or not isinstance(
                checkpoint.get("channel_versions"),
                dict,
            ):
                blockers.add(f"{identity.category}:invalid_payload")
                continue
            for channel, version in checkpoint["channel_versions"].items():
                row = self._connection.execute(
                    text(
                        """SELECT serde_type, `blob` FROM crm_langgraph_checkpoint_blobs
                           WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                             AND channel = :channel AND version = :version"""
                    ),
                    {
                        "thread_id": identity.thread_id,
                        "checkpoint_ns": identity.checkpoint_ns,
                        "channel": str(channel),
                        "version": str(version),
                    },
                ).one_or_none()
                if row is None:
                    blockers.add(f"{identity.category}:blob_missing")
                    continue
                if str(row.serde_type) == "empty":
                    continue
                try:
                    _loads_without_custom_constructors(
                        row.serde_type,
                        row.blob,
                        blocker=blocker,
                    )
                except AgentCheckpointCutoverError:
                    blockers.add(blocker)

            write_rows = self._connection.execute(
                text(
                    """SELECT serde_type, `blob`
                       FROM crm_langgraph_checkpoint_writes
                       WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                         AND checkpoint_id = :checkpoint_id"""
                ),
                {
                    "thread_id": identity.thread_id,
                    "checkpoint_ns": identity.checkpoint_ns,
                    "checkpoint_id": identity.checkpoint_id,
                },
            ).all()
            for row in write_rows:
                try:
                    _loads_without_custom_constructors(
                        row.serde_type,
                        row.blob,
                        blocker=blocker,
                    )
                except AgentCheckpointCutoverError:
                    blockers.add(blocker)

    def _validate_session_ownership(
        self,
        identities: list[CheckpointIdentity],
        blockers: set[str],
    ) -> None:
        if not _table_exists(self._connection, "crm_agent_sessions"):
            blockers.add("session:table_missing")
            return
        owners: dict[int, tuple[int, int, str]] = {}
        for row in self._connection.execute(
            text("SELECT id, team_id, user_id, session_key FROM crm_agent_sessions")
        ).all():
            owners[int(row.id)] = (int(row.team_id), int(row.user_id), str(row.session_key))
        for identity in identities:
            parsed_turn = parse_turn_root_thread(identity.thread_id)
            if parsed_turn is not None:
                team_id, user_id, session_id, _turn_token = parsed_turn
                owner = owners.get(session_id)
                if owner is None or owner[:2] != (team_id, user_id):
                    blockers.add("target_root:owner_mismatch")
                continue
            parsed_target = parse_target_root_thread(identity.thread_id)
            if parsed_target is not None:
                team_id, user_id, session_id = parsed_target
                owner = owners.get(session_id)
                if owner is None or owner[:2] != (team_id, user_id):
                    blockers.add("target_root:owner_mismatch")
                continue
            parsed_legacy = parse_legacy_root_thread(identity.thread_id)
            if parsed_legacy is None:
                continue
            team_id, user_id, session_id, session_key = parsed_legacy
            if owners.get(session_id) != (team_id, user_id, session_key):
                blockers.add("legacy_root:owner_mismatch")

    def _validate_latest_legacy_activity(
        self,
        identities: list[CheckpointIdentity],
        latest: dict[tuple[str, str], str],
        blockers: set[str],
    ) -> None:
        for identity in identities:
            if identity.category not in LEGACY_AGENT_CATEGORIES:
                continue
            if latest[(identity.thread_id, identity.checkpoint_ns)] != identity.checkpoint_id:
                continue
            if identity.pending_sends:
                blockers.add("legacy_checkpoint:active")
            if self._has_active_control_channel(identity):
                blockers.add("legacy_checkpoint:active")
            control_rows = self._connection.execute(
                text(
                    """SELECT channel FROM crm_langgraph_checkpoint_writes
                       WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                         AND checkpoint_id = :checkpoint_id"""
                ),
                {
                    "thread_id": identity.thread_id,
                    "checkpoint_ns": identity.checkpoint_ns,
                    "checkpoint_id": identity.checkpoint_id,
                },
            ).all()
            if any(str(row.channel) in {"__interrupt__", "__scheduled__", "__error__"} for row in control_rows):
                blockers.add("legacy_checkpoint:active")

    def _load_channel_value(self, identity: CheckpointIdentity, channel: str) -> object:
        checkpoint = _loads(
            self._inspection_serde,
            identity.checkpoint_type,
            identity.checkpoint_blob,
            blocker="checkpoint:unreadable",
        )
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("channel_versions"), dict):
            raise AgentCheckpointCutoverError("checkpoint:invalid_channel_versions")
        versions = checkpoint["channel_versions"]
        if channel not in versions:
            raise AgentCheckpointCutoverError("checkpoint:channel_missing")
        row = self._connection.execute(
            text(
                """SELECT serde_type, `blob` FROM crm_langgraph_checkpoint_blobs
                   WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                     AND channel = :channel AND version = :version"""
            ),
            {
                "thread_id": identity.thread_id,
                "checkpoint_ns": identity.checkpoint_ns,
                "channel": channel,
                "version": str(versions[channel]),
            },
        ).one_or_none()
        if row is None or str(row.serde_type) == "empty":
            raise AgentCheckpointCutoverError("checkpoint:blob_missing")
        return _loads(
            self._inspection_serde,
            row.serde_type,
            row.blob,
            blocker="checkpoint:unreadable",
        )

    def _has_active_control_channel(self, identity: CheckpointIdentity) -> bool:
        checkpoint = _loads(
            self._inspection_serde,
            identity.checkpoint_type,
            identity.checkpoint_blob,
            blocker="checkpoint:unreadable",
        )
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("channel_versions"), dict):
            raise AgentCheckpointCutoverError("checkpoint:invalid_channel_versions")
        for channel, version in checkpoint["channel_versions"].items():
            channel_name = str(channel)
            if not channel_name.startswith(("branch:", "join:")):
                continue
            row = self._connection.execute(
                text(
                    """SELECT serde_type, `blob` FROM crm_langgraph_checkpoint_blobs
                       WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                         AND channel = :channel AND version = :version"""
                ),
                {
                    "thread_id": identity.thread_id,
                    "checkpoint_ns": identity.checkpoint_ns,
                    "channel": channel_name,
                    "version": str(version),
                },
            ).one_or_none()
            if row is None:
                raise AgentCheckpointCutoverError("checkpoint:blob_missing")
            if str(row.serde_type) == "empty":
                continue
            value = _loads(
                self._inspection_serde,
                row.serde_type,
                row.blob,
                blocker="checkpoint:unreadable",
            )
            if value not in (None, False, "", [], (), {}):
                return True
        return False

    def _validate_customer_intelligence_physical_integrity(
        self,
        identities: list[CheckpointIdentity],
        latest: dict[tuple[str, str], str],
        blockers: set[str],
    ) -> None:
        ci_identities = [identity for identity in identities if identity.category == "customer_intelligence"]
        checkpoint_threads = {identity.thread_id for identity in ci_identities}
        physical_threads: set[str] = set()
        for table_name in ("crm_langgraph_checkpoint_blobs", "crm_langgraph_checkpoint_writes"):
            rows = self._connection.execute(
                text(
                    f"SELECT DISTINCT thread_id FROM {table_name} "
                    "WHERE thread_id LIKE 'crm_agent_customer_intelligence:%'"
                )
            ).all()
            physical_threads.update(str(row.thread_id) for row in rows)
        if physical_threads - checkpoint_threads:
            blockers.add("customer_intelligence:physical_ownership_invalid")

        by_thread: dict[str, list[CheckpointIdentity]] = {}
        for identity in ci_identities:
            by_thread.setdefault(identity.thread_id, []).append(identity)
        for thread_id, thread_identities in by_thread.items():
            parts = thread_id.split(":", 2)
            if len(parts) != 3:
                blockers.add("customer_intelligence:physical_ownership_invalid")
                continue
            team_id = _positive_int_or_none(_int_or_none(parts[1]))
            event_key = parts[2]
            checkpoint_ids = {identity.checkpoint_id for identity in thread_identities}
            parent_ids = {
                identity.parent_checkpoint_id
                for identity in thread_identities
                if identity.parent_checkpoint_id is not None
            }
            roots = [identity for identity in thread_identities if identity.parent_checkpoint_id is None]
            leaves = checkpoint_ids - parent_ids
            if (
                team_id is None
                or not event_key
                or {identity.checkpoint_ns for identity in thread_identities} != {""}
                or len(roots) != 1
                or not parent_ids <= checkpoint_ids
                or len(leaves) != 1
                or latest.get((thread_id, "")) not in leaves
            ):
                blockers.add("customer_intelligence:physical_ownership_invalid")

            referenced_blobs: set[tuple[str, str]] = set()
            for identity in thread_identities:
                try:
                    checkpoint = _loads_without_custom_constructors(
                        identity.checkpoint_type,
                        identity.checkpoint_blob,
                        blocker="customer_intelligence:physical_ownership_invalid",
                    )
                    metadata = _loads_without_custom_constructors(
                        identity.metadata_type,
                        identity.metadata_blob,
                        blocker="customer_intelligence:physical_ownership_invalid",
                    )
                except AgentCheckpointCutoverError:
                    blockers.add("customer_intelligence:physical_ownership_invalid")
                    continue
                if not isinstance(checkpoint, dict) or not isinstance(metadata, dict):
                    blockers.add("customer_intelligence:physical_ownership_invalid")
                    continue
                if (
                    metadata.get("runtime") != "crm_agent_customer_intelligence"
                    or metadata.get("runtime_namespace") != "crm_agent_customer_intelligence"
                    or metadata.get("team_id") != team_id
                    or metadata.get("event_key") != event_key
                ):
                    blockers.add("customer_intelligence:physical_ownership_invalid")
                versions = checkpoint.get("channel_versions")
                if not isinstance(versions, dict):
                    blockers.add("customer_intelligence:physical_ownership_invalid")
                    continue
                referenced_blobs.update((str(channel), str(version)) for channel, version in versions.items())

            blob_rows = self._connection.execute(
                text(
                    """SELECT checkpoint_ns, channel, version, serde_type, `blob`
                       FROM crm_langgraph_checkpoint_blobs
                       WHERE thread_id = :thread_id"""
                ),
                {"thread_id": thread_id},
            ).all()
            actual_blobs: set[tuple[str, str]] = set()
            for row in blob_rows:
                if str(row.checkpoint_ns or "") != "":
                    blockers.add("customer_intelligence:physical_ownership_invalid")
                key = (str(row.channel), str(row.version))
                if key in actual_blobs:
                    blockers.add("customer_intelligence:physical_ownership_invalid")
                actual_blobs.add(key)
                if str(row.serde_type) != "empty":
                    try:
                        _loads_without_custom_constructors(
                            row.serde_type,
                            row.blob,
                            blocker="customer_intelligence:physical_ownership_invalid",
                        )
                    except AgentCheckpointCutoverError:
                        blockers.add("customer_intelligence:physical_ownership_invalid")
            if actual_blobs != referenced_blobs:
                blockers.add("customer_intelligence:physical_ownership_invalid")

            write_rows = self._connection.execute(
                text(
                    """SELECT checkpoint_ns, checkpoint_id, serde_type, `blob`
                       FROM crm_langgraph_checkpoint_writes
                       WHERE thread_id = :thread_id"""
                ),
                {"thread_id": thread_id},
            ).all()
            for row in write_rows:
                if str(row.checkpoint_ns or "") != "" or str(row.checkpoint_id) not in checkpoint_ids:
                    blockers.add("customer_intelligence:physical_ownership_invalid")
                try:
                    _loads_without_custom_constructors(
                        row.serde_type,
                        row.blob,
                        blocker="customer_intelligence:physical_ownership_invalid",
                    )
                except AgentCheckpointCutoverError:
                    blockers.add("customer_intelligence:physical_ownership_invalid")

    def _validate_customer_intelligence_ownership(
        self,
        identities: list[CheckpointIdentity],
        latest: dict[tuple[str, str], str],
        blockers: set[str],
        *,
        as_of: datetime,
    ) -> None:
        ci_threads = {identity.thread_id for identity in identities if identity.category == "customer_intelligence"}
        if not _table_exists(self._connection, "crm_customer_intelligence_runs"):
            if ci_threads:
                blockers.add("customer_intelligence:run_table_missing")
            return
        rows = self._connection.execute(
            text(
                """SELECT event_key, event_json, tenant_id, team_id, customer_id, status,
                          attempt_count, max_attempts, lease_token, lease_expires_at
                   FROM crm_customer_intelligence_runs
                   WHERE status IN ('RUNNING', 'RETRY_PENDING')
                   ORDER BY team_id, event_key, id"""
            )
        ).all()
        for row in rows:
            event_key = str(row.event_key or "")
            team_id = _positive_int_or_none(row.team_id)
            tenant_id = _positive_int_or_none(row.tenant_id)
            customer_id = _positive_int_or_none(row.customer_id)
            attempt_count = _nonnegative_int_or_none(row.attempt_count)
            max_attempts = _positive_int_or_none(row.max_attempts)
            event = _json_object(row.event_json)
            status = str(row.status)
            invalid_identity = (
                not event_key
                or team_id is None
                or tenant_id != team_id
                or customer_id is None
                or event.get("event_key") != event_key
                or event.get("tenant_id") != team_id
                or event.get("team_id") != team_id
                or event.get("customer_id") != customer_id
                or attempt_count is None
                or attempt_count == 0
                or max_attempts is None
                or attempt_count > max_attempts
                or attempt_count == max_attempts
            )
            expected_thread = f"crm_agent_customer_intelligence:{team_id}:{event_key}"
            if invalid_identity or expected_thread not in ci_threads:
                blockers.add("customer_intelligence:active_ownership_invalid")
                continue
            root_identity = next(
                (
                    identity
                    for identity in identities
                    if identity.thread_id == expected_thread
                    and identity.checkpoint_ns == ""
                    and identity.checkpoint_id == latest.get((expected_thread, ""))
                ),
                None,
            )
            if root_identity is None:
                blockers.add("customer_intelligence:active_ownership_invalid")
                continue
            try:
                checkpoint_team_id = self._load_channel_value(root_identity, "team_id")
                checkpoint_event = _json_object(self._load_channel_value(root_identity, "event"))
            except AgentCheckpointCutoverError:
                blockers.add("customer_intelligence:active_ownership_invalid")
                continue
            if (
                checkpoint_team_id != team_id
                or checkpoint_event.get("event_key") != event_key
                or checkpoint_event.get("tenant_id") != team_id
                or checkpoint_event.get("team_id") != team_id
                or checkpoint_event.get("customer_id") != customer_id
            ):
                blockers.add("customer_intelligence:active_ownership_invalid")
                continue
            if status == "RUNNING":
                lease_expires_at = _datetime_or_none(row.lease_expires_at)
                if not isinstance(row.lease_token, str) or not row.lease_token.strip() or lease_expires_at is None:
                    blockers.add("customer_intelligence:active_ownership_invalid")
                elif lease_expires_at > as_of:
                    blockers.add("customer_intelligence:live_lease")
            elif row.lease_token is not None or row.lease_expires_at is not None:
                blockers.add("customer_intelligence:active_ownership_invalid")
            try:
                is_pending = self._has_active_control_channel(root_identity)
            except AgentCheckpointCutoverError:
                is_pending = False
            if root_identity.pending_sends or not is_pending:
                blockers.add("customer_intelligence:active_ownership_invalid")

    def _validate_active_legacy_tasks(self, blockers: set[str]) -> None:
        if not _table_exists(self._connection, "crm_agent_tasks"):
            return
        rows = self._connection.execute(
            text(
                """SELECT status, COUNT(*) AS row_count
                   FROM crm_agent_tasks
                   GROUP BY status"""
            )
        ).all()
        if any(str(row.status) in LEGACY_ACTIVE_TASK_STATUSES and int(row.row_count) > 0 for row in rows):
            blockers.add("legacy_task:active")

    def _validate_target_workflow_continuations(
        self,
        identities: list[CheckpointIdentity],
        latest: dict[tuple[str, str], str],
        blockers: set[str],
        *,
        as_of: datetime,
    ) -> None:
        target_by_locator = {
            (identity.thread_id, identity.checkpoint_ns, identity.checkpoint_id): identity
            for identity in identities
            if identity.category == "target_workflow"
        }
        root_checkpoint_ids = {
            (identity.thread_id, identity.checkpoint_id)
            for identity in identities
            if identity.category == "target_root"
        }
        pending_interrupt_locators: set[tuple[str, str, str]] = set()
        for identity in target_by_locator.values():
            if latest[(identity.thread_id, identity.checkpoint_ns)] != identity.checkpoint_id:
                continue
            rows = self._connection.execute(
                text(
                    """SELECT channel FROM crm_langgraph_checkpoint_writes
                       WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns
                         AND checkpoint_id = :checkpoint_id"""
                ),
                {
                    "thread_id": identity.thread_id,
                    "checkpoint_ns": identity.checkpoint_ns,
                    "checkpoint_id": identity.checkpoint_id,
                },
            ).all()
            if identity.pending_sends or any(str(row.channel) == "__interrupt__" for row in rows):
                pending_interrupt_locators.add((identity.thread_id, identity.checkpoint_ns, identity.checkpoint_id))

        action_locators: Counter[tuple[str, str, str]] = Counter()
        if _table_exists(self._connection, "crm_agent_ui_actions"):
            rows = self._connection.execute(
                text(
                    """SELECT team_id, user_id, session_id, target_json
                       FROM crm_agent_ui_actions
                       WHERE action_type = 'submit_interaction' AND status = 'ACTIVE'
                         AND expires_at > :as_of"""
                ),
                {"as_of": as_of},
            ).all()
            for row in rows:
                target = _json_object(row.target_json)
                try:
                    continuation = WorkflowContinuation.model_validate(target.get("workflow_continuation"))
                except ValidationError:
                    blockers.add("target_workflow:continuation_invalid")
                    continue
                root_thread_id = continuation.root_thread_id
                parsed_root = parse_turn_root_thread(root_thread_id)
                if parsed_root is None:
                    blockers.add("target_workflow:root_thread_invalid")
                    continue
                root_team_id, root_user_id, root_session_id, _turn_token = parsed_root
                if (root_team_id, root_user_id, root_session_id) != (
                    int(row.team_id),
                    int(row.user_id),
                    int(row.session_id),
                ):
                    blockers.add("target_workflow:owner_mismatch")
                    continue
                locator = (
                    root_thread_id,
                    continuation.subgraph_checkpoint_ns,
                    continuation.subgraph_checkpoint_id,
                )
                action_locators[locator] += 1
                if locator not in target_by_locator:
                    blockers.add("target_workflow:continuation_orphaned")
                if (root_thread_id, continuation.parent_checkpoint_id) not in root_checkpoint_ids:
                    blockers.add("target_workflow:parent_missing")
        elif pending_interrupt_locators:
            blockers.add("target_workflow:action_registry_missing")

        for locator in pending_interrupt_locators:
            if action_locators[locator] == 0:
                blockers.add("target_workflow:continuation_missing")
            elif action_locators[locator] > 1:
                blockers.add("target_workflow:continuation_ambiguous")
        for locator, count in action_locators.items():
            if count > 1:
                blockers.add("target_workflow:continuation_ambiguous")
            if locator not in pending_interrupt_locators:
                blockers.add("target_workflow:continuation_not_waiting")


def _positive_int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _nonnegative_int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _datetime_or_none(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _table_exists(connection: Connection, table_name: str) -> bool:
    return table_name in inspect(connection).get_table_names()


class AgentCheckpointCutoverService:
    """Validate, delete, and journal the checkpoint cutover atomically."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._reader = AgentCheckpointMatrixReader(connection)

    def run(self, *, as_of: datetime) -> AgentCheckpointCutoverResult:
        snapshot = self._reader.snapshot(as_of=as_of)
        if snapshot.blockers:
            raise AgentCheckpointCutoverError(list(snapshot.blockers))

        journal = self._journal_row()
        if journal is not None:
            result = self._post_state_result(
                snapshot=snapshot,
                already_completed=True,
                deleted_counts=(0, 0, 0),
            )
            if (
                str(journal.schema_version) != CUTOVER_SCHEMA_VERSION
                or str(journal.evidence_sha256) != result.evidence_sha256
            ):
                raise AgentCheckpointCutoverError("cutover:journal_mismatch")
            return result

        legacy_threads = sorted(snapshot.legacy_threads)
        protected_rows_before = self._retained_rows_sha256(excluded_threads=frozenset(legacy_threads))
        deleted_writes = self._delete_rows_for_threads("crm_langgraph_checkpoint_writes", legacy_threads)
        deleted_blobs = self._delete_rows_for_threads("crm_langgraph_checkpoint_blobs", legacy_threads)
        deleted_checkpoints = self._delete_rows_for_threads("crm_langgraph_checkpoints", legacy_threads)

        post_snapshot = self._reader.snapshot(as_of=as_of)
        if self._retained_rows_sha256() != protected_rows_before:
            raise AgentCheckpointCutoverError("cutover:protected_rows_changed")
        if post_snapshot.blockers:
            raise AgentCheckpointCutoverError(list(post_snapshot.blockers))
        if post_snapshot.legacy_threads:
            raise AgentCheckpointCutoverError("cutover:legacy_rows_remain")
        result = self._post_state_result(
            snapshot=post_snapshot,
            already_completed=False,
            deleted_counts=(deleted_checkpoints, deleted_blobs, deleted_writes),
        )
        self._connection.execute(
            text(
                """INSERT INTO crm_agent_checkpoint_migration_journal
                   (migration_key, schema_version, evidence_sha256)
                   VALUES (:migration_key, :schema_version, :evidence_sha256)"""
            ),
            {
                "migration_key": CUTOVER_JOURNAL_KEY,
                "schema_version": CUTOVER_SCHEMA_VERSION,
                "evidence_sha256": result.evidence_sha256,
            },
        )
        return result

    def _journal_row(self) -> Row[tuple[object, ...]] | None:
        if not _table_exists(self._connection, "crm_agent_checkpoint_migration_journal"):
            raise AgentCheckpointCutoverError("cutover:journal_table_missing")
        return self._connection.execute(
            text(
                """SELECT migration_key, schema_version, evidence_sha256
                   FROM crm_agent_checkpoint_migration_journal
                   WHERE migration_key = :migration_key"""
            ),
            {"migration_key": CUTOVER_JOURNAL_KEY},
        ).one_or_none()

    def _delete_rows_for_threads(self, table_name: str, thread_ids: list[str]) -> int:
        deleted = 0
        for thread_id in thread_ids:
            result = self._connection.execute(
                text(f"DELETE FROM {table_name} WHERE thread_id = :thread_id"),
                {"thread_id": thread_id},
            )
            deleted += max(int(result.rowcount or 0), 0)
        return deleted

    def _post_state_result(
        self,
        *,
        snapshot: CheckpointMatrixSnapshot,
        already_completed: bool,
        deleted_counts: tuple[int, int, int],
    ) -> AgentCheckpointCutoverResult:
        retained_rows_sha256 = self._retained_rows_sha256()
        stable_evidence = {
            "schema_version": CUTOVER_SCHEMA_VERSION,
            "target_root_checkpoint_count": snapshot.category_checkpoint_counts["target_root"],
            "target_workflow_checkpoint_count": snapshot.category_checkpoint_counts["target_workflow"],
            "retained_customer_intelligence_checkpoint_count": snapshot.category_checkpoint_counts[
                "customer_intelligence"
            ],
            "retained_adjacent_workflow_checkpoint_count": snapshot.category_checkpoint_counts["adjacent_workflow"],
            "retained_rows_sha256": retained_rows_sha256,
        }
        evidence_sha256 = hashlib.sha256(
            json.dumps(stable_evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        checkpoints, blobs, writes = deleted_counts
        return AgentCheckpointCutoverResult(
            already_completed=already_completed,
            deleted_legacy_checkpoint_count=checkpoints,
            deleted_legacy_blob_count=blobs,
            deleted_legacy_write_count=writes,
            target_root_checkpoint_count=stable_evidence["target_root_checkpoint_count"],
            target_workflow_checkpoint_count=stable_evidence["target_workflow_checkpoint_count"],
            retained_customer_intelligence_checkpoint_count=stable_evidence[
                "retained_customer_intelligence_checkpoint_count"
            ],
            retained_adjacent_workflow_checkpoint_count=stable_evidence["retained_adjacent_workflow_checkpoint_count"],
            retained_rows_sha256=retained_rows_sha256,
            evidence_sha256=evidence_sha256,
        )

    def _retained_rows_sha256(self, *, excluded_threads: frozenset[str] = frozenset()) -> str:
        hasher = hashlib.sha256()
        for table_name, columns, order_by in (
            (
                "crm_langgraph_checkpoints",
                "thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, "
                "checkpoint_blob, metadata_type, metadata_blob",
                "thread_id, checkpoint_ns, checkpoint_id",
            ),
            (
                "crm_langgraph_checkpoint_blobs",
                "thread_id, checkpoint_ns, channel, version, serde_type, `blob`",
                "thread_id, checkpoint_ns, channel, version",
            ),
            (
                "crm_langgraph_checkpoint_writes",
                "thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx, task_path, channel, serde_type, `blob`",
                "thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx",
            ),
        ):
            rows = self._connection.execute(text(f"SELECT {columns} FROM {table_name} ORDER BY {order_by}")).all()
            _hash_value(hasher, table_name)
            for row in rows:
                if str(row[0]) in excluded_threads:
                    continue
                for value in tuple(row):
                    _hash_value(hasher, value)
        return hasher.hexdigest()
