"""Fail-closed cleanup for terminal background runtime after Agent recovery.

This offline-only operation removes only disposable LangGraph runtime for the
customer-activity background workflows and completed Customer Intelligence run
audits. It intentionally never deletes customer, activity, follow-up, or
confirmation business records.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Final

from sqlalchemy import inspect, text

from app.services.agent.checkpoint_cutover import classify_checkpoint_identity

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Connection


BACKGROUND_RUNTIME_CLEANUP_KEY: Final = "background-runtime-cleanup-v1"
BACKGROUND_RUNTIME_CLEANUP_SCHEMA_VERSION: Final = "crm.background-runtime-cleanup.v1"
_CHECKPOINT_TABLES: Final = (
    "crm_langgraph_checkpoints",
    "crm_langgraph_checkpoint_blobs",
    "crm_langgraph_checkpoint_writes",
)
_TERMINAL_CUSTOMER_INTELLIGENCE_STATUSES: Final = frozenset({"SUCCESS", "CANCELLED", "FAILED", "EXPIRED"})
_TERMINAL_POST_COMMIT_JOB_STATUSES: Final = frozenset({"COMPLETED", "SKIPPED", "EXHAUSTED"})
_TERMINAL_CONFIRMATION_DELIVERY_STATUSES: Final = frozenset({"SENT", "SKIPPED", "EXHAUSTED", "AMBIGUOUS"})


class BackgroundRuntimeCleanupError(RuntimeError):
    """Raised if a cleanup precondition cannot prove business data is safe."""

    def __init__(self, blockers: str | list[str] | set[str]) -> None:
        self.blockers = [blockers] if isinstance(blockers, str) else sorted(set(blockers))
        super().__init__(", ".join(self.blockers))


@dataclass(frozen=True)
class TableRowCounts:
    checkpoints: int
    blobs: int
    writes: int


@dataclass(frozen=True)
class BackgroundRuntimeCleanupResult:
    """Content-free evidence of the committed, destructive maintenance action."""

    schema_version: str
    deleted_adjacent_runtime_rows: TableRowCounts
    deleted_customer_intelligence_run_count: int
    retained_post_commit_job_count: int
    retained_confirmation_case_count: int
    retained_confirmation_delivery_count: int
    evidence_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BackgroundRuntimeCleanupService:
    """Delete only proven-terminal runtime state in one locked transaction."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def run(
        self,
        *,
        stage_completed_result: Callable[[BackgroundRuntimeCleanupResult], None] | None = None,
    ) -> BackgroundRuntimeCleanupResult:
        self._require_tables()
        if self.has_completed_journal():
            raise BackgroundRuntimeCleanupError("background_cleanup:already_completed")

        adjacent_locators = self._assert_only_adjacent_checkpoint_runtime()
        self._assert_customer_intelligence_runs_are_terminal()
        self._assert_post_commit_jobs_are_terminal()
        self._assert_confirmation_deliveries_are_terminal()
        self._assert_customer_intelligence_run_dependencies_are_empty()

        deleted_runtime_rows = self._delete_checkpoint_rows(adjacent_locators)
        deleted_runs = self._delete_customer_intelligence_runs()
        self._assert_post_state()

        result = BackgroundRuntimeCleanupResult(
            schema_version=BACKGROUND_RUNTIME_CLEANUP_SCHEMA_VERSION,
            deleted_adjacent_runtime_rows=deleted_runtime_rows,
            deleted_customer_intelligence_run_count=deleted_runs,
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
                "migration_key": BACKGROUND_RUNTIME_CLEANUP_KEY,
                "schema_version": BACKGROUND_RUNTIME_CLEANUP_SCHEMA_VERSION,
                "evidence_sha256": result.evidence_sha256,
            },
        )
        return result

    def verify_committed_post_state(self, result: BackgroundRuntimeCleanupResult) -> None:
        _assert_result_evidence_is_valid(result)
        self._require_tables()
        journal = self._connection.execute(
            text(
                """SELECT schema_version, evidence_sha256
                   FROM crm_agent_checkpoint_migration_journal
                   WHERE migration_key = :migration_key"""
            ),
            {"migration_key": BACKGROUND_RUNTIME_CLEANUP_KEY},
        ).one_or_none()
        if journal is None:
            raise BackgroundRuntimeCleanupError("background_cleanup:journal_missing")
        if (
            str(journal.schema_version) != BACKGROUND_RUNTIME_CLEANUP_SCHEMA_VERSION
            or str(journal.evidence_sha256) != result.evidence_sha256
        ):
            raise BackgroundRuntimeCleanupError("background_cleanup:journal_mismatch")
        self._assert_post_state()
        if self._count_rows("crm_customer_activity_post_commit_jobs") != result.retained_post_commit_job_count:
            raise BackgroundRuntimeCleanupError("background_cleanup:post_commit_jobs_changed")
        if self._count_rows("crm_follow_up_task_confirmation_cases") != result.retained_confirmation_case_count:
            raise BackgroundRuntimeCleanupError("background_cleanup:confirmation_cases_changed")
        retained_delivery_count = self._count_rows("crm_follow_up_task_confirmation_prompt_deliveries")
        if retained_delivery_count != result.retained_confirmation_delivery_count:
            raise BackgroundRuntimeCleanupError("background_cleanup:confirmation_deliveries_changed")

    def has_completed_journal(self) -> bool:
        return (
            self._connection.execute(
                text(
                    """SELECT 1 FROM crm_agent_checkpoint_migration_journal
                   WHERE migration_key = :migration_key"""
                ),
                {"migration_key": BACKGROUND_RUNTIME_CLEANUP_KEY},
            ).one_or_none()
            is not None
        )

    def _require_tables(self) -> None:
        required = {
            "crm_agent_checkpoint_migration_journal",
            "crm_customer_intelligence_runs",
            "crm_customer_activity_post_commit_jobs",
            "crm_follow_up_task_confirmation_cases",
            "crm_follow_up_task_confirmation_prompt_deliveries",
            *_CHECKPOINT_TABLES,
        }
        missing = required - set(inspect(self._connection).get_table_names())
        if missing:
            raise BackgroundRuntimeCleanupError(
                [f"background_cleanup:missing_table:{table}" for table in sorted(missing)]
            )

    def _assert_only_adjacent_checkpoint_runtime(self) -> dict[str, set[tuple[str, str]]]:
        locators: dict[str, set[tuple[str, str]]] = defaultdict(set)
        categories: Counter[str] = Counter()
        for table_name in _CHECKPOINT_TABLES:
            rows = self._connection.execute(
                text(f"SELECT DISTINCT thread_id, checkpoint_ns FROM {table_name}")
            ).mappings()
            for row in rows:
                thread_id = str(row["thread_id"])
                checkpoint_ns = str(row["checkpoint_ns"] or "")
                category = classify_checkpoint_identity(thread_id=thread_id, checkpoint_ns=checkpoint_ns)
                categories[category] += 1
                if category == "adjacent_workflow":
                    locators[table_name].add((thread_id, checkpoint_ns))
        blockers = [
            f"background_cleanup:checkpoint_category:{category}"
            for category, count in sorted(categories.items())
            if count and category != "adjacent_workflow"
        ]
        if blockers:
            raise BackgroundRuntimeCleanupError(blockers)
        return locators

    def _assert_customer_intelligence_runs_are_terminal(self) -> None:
        statuses = self._connection.execute(
            text("SELECT DISTINCT status FROM crm_customer_intelligence_runs")
        ).scalars()
        nonterminal_statuses = {
            str(status) for status in statuses if str(status) not in _TERMINAL_CUSTOMER_INTELLIGENCE_STATUSES
        }
        blockers = [
            f"background_cleanup:customer_intelligence_nonterminal:{status}" for status in sorted(nonterminal_statuses)
        ]
        if blockers:
            raise BackgroundRuntimeCleanupError(blockers)

    def _assert_post_commit_jobs_are_terminal(self) -> None:
        statuses = self._connection.execute(
            text("SELECT DISTINCT status FROM crm_customer_activity_post_commit_jobs")
        ).scalars()
        nonterminal_statuses = {
            str(status) for status in statuses if str(status) not in _TERMINAL_POST_COMMIT_JOB_STATUSES
        }
        blockers = [
            f"background_cleanup:post_commit_job_nonterminal:{status}" for status in sorted(nonterminal_statuses)
        ]
        if blockers:
            raise BackgroundRuntimeCleanupError(blockers)

    def _assert_confirmation_deliveries_are_terminal(self) -> None:
        statuses = self._connection.execute(
            text("SELECT DISTINCT status FROM crm_follow_up_task_confirmation_prompt_deliveries")
        ).scalars()
        blockers = [
            f"background_cleanup:confirmation_delivery_nonterminal:{status}"
            for status in sorted(
                {str(status) for status in statuses if str(status) not in _TERMINAL_CONFIRMATION_DELIVERY_STATUSES}
            )
        ]
        if blockers:
            raise BackgroundRuntimeCleanupError(blockers)

    def _assert_customer_intelligence_run_dependencies_are_empty(self) -> None:
        blockers: list[str] = []
        inspector = inspect(self._connection)
        for table_name in inspector.get_table_names():
            if table_name == "crm_customer_intelligence_runs":
                continue
            for foreign_key in inspector.get_foreign_keys(table_name):
                if foreign_key.get("referred_table") != "crm_customer_intelligence_runs":
                    continue
                columns = [str(column) for column in foreign_key.get("constrained_columns") or []]
                if not columns:
                    blockers.append(f"background_cleanup:customer_intelligence_dependency:{table_name}")
                    continue
                null_checks = " AND ".join(f"{_quote_identifier(column)} IS NOT NULL" for column in columns)
                dependency_query = text(f"SELECT 1 FROM {_quote_identifier(table_name)} WHERE {null_checks} LIMIT 1")
                if self._connection.execute(dependency_query).first():
                    blockers.append(f"background_cleanup:customer_intelligence_dependency:{table_name}")
        if blockers:
            raise BackgroundRuntimeCleanupError(blockers)

    def _delete_checkpoint_rows(self, locators: dict[str, set[tuple[str, str]]]) -> TableRowCounts:
        deleted: dict[str, int] = {}
        for table_name in _CHECKPOINT_TABLES:
            row_count = 0
            for thread_id, checkpoint_ns in sorted(locators.get(table_name, set())):
                result = self._connection.execute(
                    text(f"DELETE FROM {table_name} WHERE thread_id = :thread_id AND checkpoint_ns = :checkpoint_ns"),
                    {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns},
                )
                row_count += max(int(result.rowcount or 0), 0)
            deleted[table_name] = row_count
        return TableRowCounts(
            checkpoints=deleted["crm_langgraph_checkpoints"],
            blobs=deleted["crm_langgraph_checkpoint_blobs"],
            writes=deleted["crm_langgraph_checkpoint_writes"],
        )

    def _delete_customer_intelligence_runs(self) -> int:
        result = self._connection.execute(text("DELETE FROM crm_customer_intelligence_runs"))
        return max(int(result.rowcount or 0), 0)

    def _assert_post_state(self) -> None:
        for table_name in _CHECKPOINT_TABLES:
            if self._count_rows(table_name) != 0:
                raise BackgroundRuntimeCleanupError(f"background_cleanup:checkpoint_rows_remain:{table_name}")
        if self._count_rows("crm_customer_intelligence_runs") != 0:
            raise BackgroundRuntimeCleanupError("background_cleanup:customer_intelligence_runs_remain")

    def _count_rows(self, table_name: str) -> int:
        return int(self._connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _result_without_evidence(result: BackgroundRuntimeCleanupResult) -> bytes:
    payload = result.to_dict()
    payload["evidence_sha256"] = ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _assert_result_evidence_is_valid(result: BackgroundRuntimeCleanupResult) -> None:
    if result.schema_version != BACKGROUND_RUNTIME_CLEANUP_SCHEMA_VERSION:
        raise BackgroundRuntimeCleanupError("background_cleanup:completed_evidence_invalid")
    if result.evidence_sha256 != _sha256(_result_without_evidence(result)):
        raise BackgroundRuntimeCleanupError("background_cleanup:completed_evidence_invalid")
