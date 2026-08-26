"""Fail-closed, offline cleanup of completed Agent task-list history.

The Agent task panel reads durable operation projections rather than the
LangGraph checkpoint tables. This maintenance seam removes only terminal
operation projections and their append-only events; it never touches CRM
business records or the post-commit/confirmation work queues.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Final

from sqlalchemy import inspect, text

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Connection


AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_KEY: Final = "agent-async-operation-history-cleanup-v1"
AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_SCHEMA_VERSION: Final = "crm.agent-async-operation-history-cleanup.v1"
_TERMINAL_OPERATION_STATUSES: Final = frozenset({"SUCCEEDED", "DEGRADED", "FAILED", "CANCELLED"})
_PROTECTED_TABLES: Final = (
    "crm_customer_activity_post_commit_jobs",
    "crm_follow_up_task_confirmation_cases",
    "crm_follow_up_task_confirmation_prompt_deliveries",
)


class AgentAsyncOperationHistoryCleanupError(RuntimeError):
    """Raised when deletion cannot be proven to be limited to terminal UI history."""

    def __init__(self, blockers: str | list[str] | set[str]) -> None:
        self.blockers = [blockers] if isinstance(blockers, str) else sorted(set(blockers))
        super().__init__(", ".join(self.blockers))


@dataclass(frozen=True)
class AgentAsyncOperationHistoryCleanupResult:
    """Content-free evidence for this destructive, offline-only maintenance action."""

    schema_version: str
    deleted_operation_count: int
    deleted_event_count: int
    retained_post_commit_job_count: int
    retained_confirmation_case_count: int
    retained_confirmation_delivery_count: int
    evidence_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AgentAsyncOperationHistoryCleanupService:
    """Delete only terminal Agent task-list projections in a locked transaction."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def run(
        self,
        *,
        stage_completed_result: Callable[[AgentAsyncOperationHistoryCleanupResult], None] | None = None,
    ) -> AgentAsyncOperationHistoryCleanupResult:
        self._require_tables()
        if self.has_completed_journal():
            raise AgentAsyncOperationHistoryCleanupError("agent_async_operation_history_cleanup:already_completed")

        self._assert_all_operations_are_terminal()
        self._assert_no_unexpected_operation_dependencies()

        deleted_events = self._delete_all_events()
        deleted_operations = self._delete_all_operations()
        self._assert_post_state()

        result = AgentAsyncOperationHistoryCleanupResult(
            schema_version=AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_SCHEMA_VERSION,
            deleted_operation_count=deleted_operations,
            deleted_event_count=deleted_events,
            retained_post_commit_job_count=self._count_rows("crm_customer_activity_post_commit_jobs"),
            retained_confirmation_case_count=self._count_rows("crm_follow_up_task_confirmation_cases"),
            retained_confirmation_delivery_count=self._count_rows("crm_follow_up_task_confirmation_prompt_deliveries"),
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
                "migration_key": AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_KEY,
                "schema_version": AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_SCHEMA_VERSION,
                "evidence_sha256": result.evidence_sha256,
            },
        )
        return result

    def verify_committed_post_state(self, result: AgentAsyncOperationHistoryCleanupResult) -> None:
        _assert_result_evidence_is_valid(result)
        self._require_tables()
        journal = self._connection.execute(
            text(
                """SELECT schema_version, evidence_sha256
                   FROM crm_agent_checkpoint_migration_journal
                   WHERE migration_key = :migration_key"""
            ),
            {"migration_key": AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_KEY},
        ).one_or_none()
        if journal is None:
            raise AgentAsyncOperationHistoryCleanupError("agent_async_operation_history_cleanup:journal_missing")
        if (
            str(journal.schema_version) != AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_SCHEMA_VERSION
            or str(journal.evidence_sha256) != result.evidence_sha256
        ):
            raise AgentAsyncOperationHistoryCleanupError("agent_async_operation_history_cleanup:journal_mismatch")
        self._assert_post_state()
        expected_retained_counts = (
            ("crm_customer_activity_post_commit_jobs", result.retained_post_commit_job_count, "post_commit_jobs"),
            ("crm_follow_up_task_confirmation_cases", result.retained_confirmation_case_count, "confirmation_cases"),
            (
                "crm_follow_up_task_confirmation_prompt_deliveries",
                result.retained_confirmation_delivery_count,
                "confirmation_deliveries",
            ),
        )
        for table_name, expected_count, label in expected_retained_counts:
            if self._count_rows(table_name) != expected_count:
                raise AgentAsyncOperationHistoryCleanupError(
                    f"agent_async_operation_history_cleanup:{label}_changed"
                )

    def has_completed_journal(self) -> bool:
        return (
            self._connection.execute(
                text(
                    """SELECT 1 FROM crm_agent_checkpoint_migration_journal
                       WHERE migration_key = :migration_key"""
                ),
                {"migration_key": AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_KEY},
            ).one_or_none()
            is not None
        )

    def _require_tables(self) -> None:
        required = {
            "crm_agent_checkpoint_migration_journal",
            "crm_agent_async_operations",
            "crm_agent_async_operation_events",
            *_PROTECTED_TABLES,
        }
        missing = required - set(inspect(self._connection).get_table_names())
        if missing:
            raise AgentAsyncOperationHistoryCleanupError(
                [f"agent_async_operation_history_cleanup:missing_table:{table}" for table in sorted(missing)]
            )

    def _assert_all_operations_are_terminal(self) -> None:
        statuses = self._connection.execute(text("SELECT DISTINCT status FROM crm_agent_async_operations")).scalars()
        nonterminal_statuses = {str(status) for status in statuses if str(status) not in _TERMINAL_OPERATION_STATUSES}
        if nonterminal_statuses:
            raise AgentAsyncOperationHistoryCleanupError(
                [
                    f"agent_async_operation_history_cleanup:nonterminal_status:{status}"
                    for status in sorted(nonterminal_statuses)
                ]
            )

    def _assert_no_unexpected_operation_dependencies(self) -> None:
        inspector = inspect(self._connection)
        blockers: list[str] = []
        for table_name in inspector.get_table_names():
            if table_name == "crm_agent_async_operations":
                continue
            foreign_keys = [
                foreign_key
                for foreign_key in inspector.get_foreign_keys(table_name)
                if foreign_key.get("referred_table") == "crm_agent_async_operations"
            ]
            if not foreign_keys:
                continue
            if table_name == "crm_agent_async_operation_events":
                continue
            for foreign_key in foreign_keys:
                columns = [str(column) for column in foreign_key.get("constrained_columns") or []]
                if not columns:
                    blockers.append(f"agent_async_operation_history_cleanup:unexpected_dependency:{table_name}")
                    continue
                non_null_clause = " AND ".join(f"{_quote_identifier(column)} IS NOT NULL" for column in columns)
                if self._connection.execute(
                    text(f"SELECT 1 FROM {_quote_identifier(table_name)} WHERE {non_null_clause} LIMIT 1")
                ).first():
                    blockers.append(f"agent_async_operation_history_cleanup:unexpected_dependency:{table_name}")
        if blockers:
            raise AgentAsyncOperationHistoryCleanupError(blockers)

    def _delete_all_events(self) -> int:
        return max(int(self._connection.execute(text("DELETE FROM crm_agent_async_operation_events")).rowcount or 0), 0)

    def _delete_all_operations(self) -> int:
        return max(int(self._connection.execute(text("DELETE FROM crm_agent_async_operations")).rowcount or 0), 0)

    def _assert_post_state(self) -> None:
        for table_name in ("crm_agent_async_operations", "crm_agent_async_operation_events"):
            if self._count_rows(table_name) != 0:
                raise AgentAsyncOperationHistoryCleanupError(
                    f"agent_async_operation_history_cleanup:rows_remain:{table_name}"
                )

    def _count_rows(self, table_name: str) -> int:
        return int(self._connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _result_without_evidence(result: AgentAsyncOperationHistoryCleanupResult) -> bytes:
    payload = result.to_dict()
    payload["evidence_sha256"] = ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _assert_result_evidence_is_valid(result: AgentAsyncOperationHistoryCleanupResult) -> None:
    if result.schema_version != AGENT_ASYNC_OPERATION_HISTORY_CLEANUP_SCHEMA_VERSION:
        raise AgentAsyncOperationHistoryCleanupError("agent_async_operation_history_cleanup:completed_evidence_invalid")
    if result.evidence_sha256 != _sha256(_result_without_evidence(result)):
        raise AgentAsyncOperationHistoryCleanupError("agent_async_operation_history_cleanup:completed_evidence_invalid")
