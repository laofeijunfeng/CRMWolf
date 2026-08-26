#!/usr/bin/env python3
"""Run the controlled, one-time CRM Agent historical-message migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.agent.message_migration import (
    AgentMessageMigrationBatchResult,
    AgentMessageMigrationError,
    AgentMessageMigrationService,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy import Engine


class AgentMessageMigrationRunReport(BaseModel):
    """Content-free evidence for one complete historical-message migration run."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["crm.agent.message-migration-run.v1"] = "crm.agent.message-migration-run.v1"
    status: Literal["IN_PROGRESS", "COMPLETED", "FAILED"]
    failure_code: Literal["INVALID_SOURCE_DATA", "INVALID_ARGUMENT", "MIGRATION_EXECUTION_FAILED"] | None = None
    start_after_id: int
    last_id: int | None = Field(default=None, gt=0)
    batch_size: int
    batch_count: int = Field(ge=0)
    source_row_count: int = Field(ge=0)
    target_row_count: int = Field(ge=0)
    migrated_row_count: int = Field(ge=0)
    schema_validated_count: int = Field(ge=0)
    batches: list[AgentMessageMigrationBatchResult]


def _build_run_report(
    *,
    status: Literal["IN_PROGRESS", "COMPLETED", "FAILED"],
    failure_code: Literal["INVALID_SOURCE_DATA", "INVALID_ARGUMENT", "MIGRATION_EXECUTION_FAILED"] | None,
    start_after_id: int,
    batch_size: int,
    batches: list[AgentMessageMigrationBatchResult],
) -> AgentMessageMigrationRunReport:
    return AgentMessageMigrationRunReport(
        status=status,
        failure_code=failure_code,
        start_after_id=start_after_id,
        last_id=batches[-1].last_id if batches else None,
        batch_size=batch_size,
        batch_count=len(batches),
        source_row_count=sum(batch.source_row_count for batch in batches),
        target_row_count=sum(batch.target_row_count for batch in batches),
        migrated_row_count=sum(batch.migrated_row_count for batch in batches),
        schema_validated_count=sum(batch.schema_validated_count for batch in batches),
        batches=batches,
    )


def _run_message_migration(
    engine: Engine,
    *,
    start_after_id: int,
    batch_size: int,
    on_progress: Callable[[AgentMessageMigrationRunReport], None] | None = None,
) -> AgentMessageMigrationRunReport:
    if start_after_id < 0:
        raise ValueError("start_after_id must not be negative")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    service = AgentMessageMigrationService(engine)
    cursor = start_after_id
    batches: list[AgentMessageMigrationBatchResult] = []
    while True:
        batch = service.migrate_batch(after_id=cursor, batch_size=batch_size)
        if batch.source_row_count == 0:
            break
        batches.append(batch)
        if on_progress is not None:
            on_progress(
                _build_run_report(
                    status="IN_PROGRESS",
                    failure_code=None,
                    start_after_id=start_after_id,
                    batch_size=batch_size,
                    batches=batches,
                )
            )
        if batch.last_id is None:
            raise RuntimeError("non-empty migration batch did not return a cursor")
        cursor = batch.last_id
        if not batch.has_more:
            break

    return _build_run_report(
        status="COMPLETED",
        failure_code=None,
        start_after_id=start_after_id,
        batch_size=batch_size,
        batches=batches,
    )


def run_message_migration(
    engine: Engine,
    *,
    start_after_id: int = 0,
    batch_size: int = 1000,
) -> AgentMessageMigrationRunReport:
    """Migrate all rows after the cursor, committing and validating one batch at a time."""

    return _run_message_migration(
        engine,
        start_after_id=start_after_id,
        batch_size=batch_size,
    )


def _write_report(path: Path, report: AgentMessageMigrationRunReport) -> None:
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(payload + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _failure_code(error: Exception) -> Literal["INVALID_SOURCE_DATA", "INVALID_ARGUMENT", "MIGRATION_EXECUTION_FAILED"]:
    if isinstance(error, AgentMessageMigrationError):
        return "INVALID_SOURCE_DATA"
    if isinstance(error, ValueError):
        return "INVALID_ARGUMENT"
    return "MIGRATION_EXECUTION_FAILED"


def execute_message_migration(
    engine: Engine,
    *,
    output_path: Path,
    start_after_id: int = 0,
    batch_size: int = 1000,
) -> int:
    """Execute the migration while atomically persisting content-free progress evidence."""

    latest_report = _build_run_report(
        status="IN_PROGRESS",
        failure_code=None,
        start_after_id=start_after_id,
        batch_size=batch_size,
        batches=[],
    )
    _write_report(output_path, latest_report)

    def persist_progress(report: AgentMessageMigrationRunReport) -> None:
        nonlocal latest_report
        latest_report = report
        _write_report(output_path, report)

    try:
        completed_report = _run_message_migration(
            engine,
            start_after_id=start_after_id,
            batch_size=batch_size,
            on_progress=persist_progress,
        )
    except Exception as error:
        failed_report = latest_report.model_copy(update={"status": "FAILED", "failure_code": _failure_code(error)})
        _write_report(output_path, failed_report)
        return 1

    _write_report(output_path, completed_report)
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows per committed batch (default: 1000).")
    parser.add_argument("--start-after-id", type=int, default=0, help="Resume after this primary-key cursor.")
    parser.add_argument("--output", type=Path, required=True, help="Path for the content-free JSON evidence report.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required acknowledgement that the command will update historical message rows.",
    )
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("--execute is required")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    from app.core.database import engine

    return execute_message_migration(
        engine,
        output_path=args.output,
        start_after_id=args.start_after_id,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    raise SystemExit(main())
