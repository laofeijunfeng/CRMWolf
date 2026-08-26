"""Auditable forward recovery after a forced one-version Agent schema upgrade.

This offline-only service exists for the exceptional case where the new Agent
schema was applied before the ordinary migration gate could finish and no
pre-upgrade database restore point exists. It deliberately accepts *only* an
empty target runtime, terminal Customer Intelligence runs, fully legacy Agent
messages, and known legacy Agent checkpoint ownership. It never interprets
checkpoint payloads and never deletes adjacent workflow data.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import inspect, text

from app.services.agent.checkpoint_cutover import (
    LEGACY_AGENT_CATEGORIES,
    CheckpointCategory,
    classify_checkpoint_identity,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from sqlalchemy.engine import Connection, RowMapping


FORCED_SCHEMA_RECOVERY_KEY: Final = "agent-forced-schema-recovery-v1"
FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION: Final = "crm.agent.forced-schema-recovery.v1"
_CHECKPOINT_TABLES: Final = (
    "crm_langgraph_checkpoints",
    "crm_langgraph_checkpoint_blobs",
    "crm_langgraph_checkpoint_writes",
)
_TERMINAL_CUSTOMER_INTELLIGENCE_STATUSES: Final = frozenset({"SUCCESS", "CANCELLED", "FAILED", "EXPIRED"})
_DELETABLE_CHECKPOINT_CATEGORIES: Final = LEGACY_AGENT_CATEGORIES | frozenset({"customer_intelligence"})
_BLOCKING_CHECKPOINT_CATEGORIES: Final = frozenset({"target_root", "target_workflow", "unknown"})


class ForcedSchemaRecoveryError(RuntimeError):
    """The destructive forward-recovery preconditions are not satisfied."""

    def __init__(self, blockers: str | Iterable[str]) -> None:
        values = [blockers] if isinstance(blockers, str) else sorted(set(blockers))
        self.blockers = values
        super().__init__(", ".join(values))


@dataclass(frozen=True)
class TableRowCounts:
    checkpoints: int
    blobs: int
    writes: int


@dataclass(frozen=True)
class ForcedSchemaRecoveryResult:
    """Content-free committed result for a forced Agent forward recovery."""

    schema_version: str
    already_completed: bool
    deleted_agent_message_count: int
    deleted_legacy_checkpoint_rows: TableRowCounts
    deleted_customer_intelligence_checkpoint_rows: TableRowCounts
    retained_adjacent_checkpoint_rows: TableRowCounts
    retained_adjacent_rows_sha256: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ForcedSchemaRecoveryService:
    """Fail closed before resetting unrecoverable historical Agent runtime data."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def run(
        self,
        *,
        stage_completed_result: Callable[[ForcedSchemaRecoveryResult], None] | None = None,
    ) -> ForcedSchemaRecoveryResult:
        self._require_tables()
        self._assert_not_already_completed()
        rows_by_category = self._classify_checkpoint_rows()
        self._assert_only_deletable_or_adjacent(rows_by_category)
        self._assert_customer_intelligence_runs_are_terminal()
        self._assert_agent_message_dependencies_are_empty()
        message_count = self._assert_messages_are_fully_legacy()

        retained_before = self._fingerprint_rows("adjacent_workflow")
        retained_counts = self._row_counts(rows_by_category["adjacent_workflow"])
        deleted_legacy_counts = self._row_counts_for_categories(rows_by_category, LEGACY_AGENT_CATEGORIES)
        deleted_ci_counts = self._row_counts(rows_by_category["customer_intelligence"])

        self._delete_checkpoint_rows(rows_by_category, _DELETABLE_CHECKPOINT_CATEGORIES)
        deleted_messages = self._connection.execute(text("DELETE FROM crm_agent_messages")).rowcount
        if deleted_messages != message_count:
            raise ForcedSchemaRecoveryError("recovery:agent_message_delete_count_mismatch")

        post_rows_by_category = self._classify_checkpoint_rows()
        self._assert_post_state(post_rows_by_category)
        if self._fingerprint_rows("adjacent_workflow") != retained_before:
            raise ForcedSchemaRecoveryError("recovery:adjacent_rows_changed")

        result = ForcedSchemaRecoveryResult(
            schema_version=FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION,
            already_completed=False,
            deleted_agent_message_count=deleted_messages,
            deleted_legacy_checkpoint_rows=deleted_legacy_counts,
            deleted_customer_intelligence_checkpoint_rows=deleted_ci_counts,
            retained_adjacent_checkpoint_rows=retained_counts,
            retained_adjacent_rows_sha256=retained_before,
            evidence_sha256="",
        )
        result = replace(result, evidence_sha256=_sha256(_result_without_evidence(result)))
        if stage_completed_result is not None:
            stage_completed_result(result)
        self._connection.execute(
            text(
                """INSERT INTO crm_agent_checkpoint_migration_journal
                   (migration_key, schema_version, evidence_sha256)
                   VALUES (:migration_key, :schema_version, :evidence_sha256)"""
            ),
            {
                "migration_key": FORCED_SCHEMA_RECOVERY_KEY,
                "schema_version": FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION,
                "evidence_sha256": result.evidence_sha256,
            },
        )
        return result

    def verify_committed_post_state(self, result: ForcedSchemaRecoveryResult) -> None:
        """Verify a committed recovery before publishing staged evidence."""
        _assert_result_evidence_is_valid(result)
        self._require_tables()
        journal = self._connection.execute(
            text(
                """SELECT schema_version, evidence_sha256
                   FROM crm_agent_checkpoint_migration_journal
                   WHERE migration_key = :migration_key"""
            ),
            {"migration_key": FORCED_SCHEMA_RECOVERY_KEY},
        ).one_or_none()
        if journal is None:
            raise ForcedSchemaRecoveryError("recovery:journal_missing")
        if (
            str(journal.schema_version) != FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION
            or str(journal.evidence_sha256) != result.evidence_sha256
        ):
            raise ForcedSchemaRecoveryError("recovery:journal_mismatch")
        self._assert_customer_intelligence_runs_are_terminal()
        self._assert_agent_message_dependencies_are_empty()
        if self._assert_messages_are_fully_legacy() != 0:
            raise ForcedSchemaRecoveryError("recovery:agent_messages_remain")
        self._assert_post_state(self._classify_checkpoint_rows())
        retained_rows = self._classify_checkpoint_rows()["adjacent_workflow"]
        if self._row_counts(retained_rows) != result.retained_adjacent_checkpoint_rows:
            raise ForcedSchemaRecoveryError("recovery:adjacent_row_count_changed")
        if self._fingerprint_rows("adjacent_workflow") != result.retained_adjacent_rows_sha256:
            raise ForcedSchemaRecoveryError("recovery:adjacent_rows_changed")

    def has_completed_journal(self) -> bool:
        """Return whether this recovery's immutable completion journal exists."""
        journal = self._connection.execute(
            text(
                """SELECT 1
                   FROM crm_agent_checkpoint_migration_journal
                   WHERE migration_key = :migration_key"""
            ),
            {"migration_key": FORCED_SCHEMA_RECOVERY_KEY},
        ).one_or_none()
        return journal is not None

    def _require_tables(self) -> None:
        existing_tables = set(inspect(self._connection).get_table_names())
        required_tables = {
            "crm_agent_checkpoint_migration_journal",
            "crm_agent_messages",
            "crm_customer_intelligence_runs",
            *_CHECKPOINT_TABLES,
        }
        missing_tables = required_tables - existing_tables
        if missing_tables:
            raise ForcedSchemaRecoveryError(
                f"recovery:missing_table:{table_name}" for table_name in sorted(missing_tables)
            )

    def _assert_not_already_completed(self) -> None:
        if self.has_completed_journal():
            raise ForcedSchemaRecoveryError("recovery:already_completed")

    def _classify_checkpoint_rows(self) -> dict[CheckpointCategory, dict[str, set[tuple[str, str]]]]:
        rows_by_category: dict[CheckpointCategory, dict[str, set[tuple[str, str]]]] = {
            category: defaultdict(set)
            for category in (
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
        }
        for table_name in _CHECKPOINT_TABLES:
            rows = self._connection.execute(
                text(f"SELECT DISTINCT thread_id, checkpoint_ns FROM {table_name}")
            ).mappings()
            for row in rows:
                thread_id = str(row["thread_id"])
                checkpoint_ns = str(row["checkpoint_ns"] or "")
                category = classify_checkpoint_identity(thread_id=thread_id, checkpoint_ns=checkpoint_ns)
                rows_by_category[category][table_name].add((thread_id, checkpoint_ns))
        return rows_by_category

    def _assert_only_deletable_or_adjacent(
        self,
        rows_by_category: dict[CheckpointCategory, dict[str, set[tuple[str, str]]]],
    ) -> None:
        blockers = [
            f"recovery:checkpoint_category:{category}"
            for category in _BLOCKING_CHECKPOINT_CATEGORIES
            if any(rows_by_category[category].values())
        ]
        if blockers:
            raise ForcedSchemaRecoveryError(blockers)

    def _assert_customer_intelligence_runs_are_terminal(self) -> None:
        statuses = self._connection.execute(
            text("SELECT DISTINCT status FROM crm_customer_intelligence_runs")
        ).scalars()
        nonterminal = sorted(
            {
                str(status)
                for status in statuses
                if str(status) not in _TERMINAL_CUSTOMER_INTELLIGENCE_STATUSES
            }
        )
        if nonterminal:
            raise ForcedSchemaRecoveryError(
                f"recovery:customer_intelligence_nonterminal:{status}" for status in nonterminal
            )

    def _assert_agent_message_dependencies_are_empty(self) -> None:
        inspector = inspect(self._connection)
        blockers: list[str] = []
        for table_name in inspector.get_table_names():
            if table_name == "crm_agent_messages":
                continue
            for foreign_key in inspector.get_foreign_keys(table_name):
                if foreign_key.get("referred_table") != "crm_agent_messages":
                    continue
                constrained_columns = foreign_key.get("constrained_columns") or []
                if not constrained_columns:
                    blockers.append(f"recovery:agent_message_dependency:{table_name}")
                    continue
                null_checks = " AND ".join(
                    f"{_quote_identifier(str(column_name))} IS NOT NULL"
                    for column_name in constrained_columns
                )
                count = int(
                    self._connection.execute(
                        text(
                            f"SELECT COUNT(*) FROM {_quote_identifier(table_name)} "
                            f"WHERE {null_checks}"
                        )
                    ).scalar_one()
                )
                if count:
                    blockers.append(f"recovery:agent_message_dependency:{table_name}")
        if blockers:
            raise ForcedSchemaRecoveryError(blockers)

    def _assert_messages_are_fully_legacy(self) -> int:
        row = self._connection.execute(
            text(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN turn_id IS NOT NULL OR ui_json IS NOT NULL THEN 1 ELSE 0 END) AS migrated
                   FROM crm_agent_messages"""
            )
        ).mappings().one()
        total = int(row["total"])
        migrated = int(row["migrated"] or 0)
        if migrated:
            raise ForcedSchemaRecoveryError("recovery:agent_message_partial_target_state")
        return total

    def _row_counts(self, locators_by_table: dict[str, set[tuple[str, str]]]) -> TableRowCounts:
        return TableRowCounts(
            checkpoints=self._count_rows(
                "crm_langgraph_checkpoints",
                locators_by_table["crm_langgraph_checkpoints"],
            ),
            blobs=self._count_rows(
                "crm_langgraph_checkpoint_blobs",
                locators_by_table["crm_langgraph_checkpoint_blobs"],
            ),
            writes=self._count_rows(
                "crm_langgraph_checkpoint_writes",
                locators_by_table["crm_langgraph_checkpoint_writes"],
            ),
        )

    def _row_counts_for_categories(
        self,
        rows_by_category: dict[CheckpointCategory, dict[str, set[tuple[str, str]]]],
        categories: frozenset[CheckpointCategory],
    ) -> TableRowCounts:
        locators_by_table: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for category in categories:
            for table_name, locators in rows_by_category[category].items():
                locators_by_table[table_name].update(locators)
        return self._row_counts(locators_by_table)

    def _count_rows(self, table_name: str, locators: set[tuple[str, str]]) -> int:
        return sum(self._count_rows_for_locator(table_name, locator) for locator in locators)

    def _count_rows_for_locator(self, table_name: str, locator: tuple[str, str]) -> int:
        thread_id, checkpoint_ns = locator
        return int(
            self._connection.execute(
                text(
                    f"""SELECT COUNT(*) FROM {table_name}
                        WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns"""
                ),
                {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns},
            ).scalar_one()
        )

    def _delete_checkpoint_rows(
        self,
        rows_by_category: dict[CheckpointCategory, dict[str, set[tuple[str, str]]]],
        categories: frozenset[CheckpointCategory],
    ) -> None:
        for table_name in reversed(_CHECKPOINT_TABLES):
            locators: set[tuple[str, str]] = set()
            for category in categories:
                locators.update(rows_by_category[category][table_name])
            for thread_id, checkpoint_ns in locators:
                self._connection.execute(
                    text(
                        f"""DELETE FROM {table_name}
                            WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns"""
                    ),
                    {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns},
                )

    def _assert_post_state(
        self,
        rows_by_category: dict[CheckpointCategory, dict[str, set[tuple[str, str]]]],
    ) -> None:
        blockers = [
            f"recovery:post_state:{category}"
            for category in _DELETABLE_CHECKPOINT_CATEGORIES | _BLOCKING_CHECKPOINT_CATEGORIES
            if any(rows_by_category[category].values())
        ]
        if blockers:
            raise ForcedSchemaRecoveryError(blockers)

    def _fingerprint_rows(self, category: CheckpointCategory) -> str:
        locators_by_table = self._classify_checkpoint_rows()[category]
        digest = hashlib.sha256()
        for table_name in _CHECKPOINT_TABLES:
            for thread_id, checkpoint_ns in sorted(locators_by_table[table_name]):
                rows = self._connection.execute(
                    text(
                        f"""SELECT * FROM {table_name}
                            WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns"""
                    ),
                    {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns},
                ).mappings()
                for row in sorted(rows, key=_row_sort_key):
                    digest.update(_sha256(_content_free_row(row)).encode("ascii"))
        return digest.hexdigest()


def _result_without_evidence(result: ForcedSchemaRecoveryResult) -> dict[str, object]:
    payload = result.to_dict()
    payload.pop("evidence_sha256")
    return payload


def _assert_result_evidence_is_valid(result: ForcedSchemaRecoveryResult) -> None:
    counts = (
        result.deleted_legacy_checkpoint_rows,
        result.deleted_customer_intelligence_checkpoint_rows,
        result.retained_adjacent_checkpoint_rows,
    )
    if (
        result.schema_version != FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION
        or result.already_completed
        or result.deleted_agent_message_count < 0
        or any(value < 0 for count in counts for value in asdict(count).values())
        or result.evidence_sha256 != _sha256(_result_without_evidence(result))
    ):
        raise ForcedSchemaRecoveryError("recovery:completed_evidence_invalid")


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _row_sort_key(row: RowMapping) -> str:
    return json.dumps(_content_free_row(row), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _content_free_row(row: RowMapping) -> dict[str, object]:
    return {str(key): _content_free_value(value) for key, value in row.items()}


def _content_free_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _sha256(payload: object) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
