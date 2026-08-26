#!/usr/bin/env python3
"""Execute the single-version CRM Agent checkpoint cutover."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from contextlib import suppress
from datetime import datetime  # noqa: TC003 - Pydantic resolves this annotation at runtime.
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.agent.checkpoint_cutover import (
    AgentCheckpointCutoverError,
    AgentCheckpointCutoverResult,
    AgentCheckpointCutoverService,
)
from app.services.agent.migration_time import parse_business_as_of

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Engine


class CheckpointCutoverRunReport(BaseModel):
    """Durable, content-free evidence for one cutover command invocation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["crm.agent.checkpoint-cutover-run.v1"] = "crm.agent.checkpoint-cutover-run.v1"
    scope_status: Literal["IN_PROGRESS", "COMPLETED", "FAILED"]
    as_of: datetime
    failure_code: Literal["RELEASE_GATE_BLOCKED", "CUTOVER_EXECUTION_FAILED"] | None = None
    blockers: list[str] = Field(default_factory=list)
    result: AgentCheckpointCutoverResult | None = None


def _report_payload(report: CheckpointCutoverRunReport) -> str:
    return (
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _write_durable_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.writing.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temp_path.replace(path)
    _fsync_directory(path.parent)


def _write_report(path: Path, report: CheckpointCutoverRunReport) -> None:
    _write_durable_text(path, _report_payload(report))


def _stage_completed_report(
    output_path: Path,
    report: CheckpointCutoverRunReport,
) -> Path:
    staged_path = output_path.with_name(f".{output_path.name}.completed.tmp")
    _write_durable_text(staged_path, _report_payload(report))
    return staged_path


def _read_completed_report(path: Path) -> CheckpointCutoverRunReport:
    report = CheckpointCutoverRunReport.model_validate_json(path.read_text(encoding="utf-8"))
    if report.scope_status != "COMPLETED" or report.result is None:
        raise RuntimeError("cutover report is not completed")
    return report


def _verify_completed_report(
    engine: Engine,
    report: CheckpointCutoverRunReport,
    *,
    expected_as_of: datetime,
) -> None:
    if report.as_of != expected_as_of:
        raise RuntimeError("cutover report business cutoff differs from this invocation")
    if report.result is None:
        raise RuntimeError("completed cutover report has no result")
    with engine.begin() as connection:
        verified = AgentCheckpointCutoverService(connection).run(as_of=report.as_of)
        if (
            verified.evidence_sha256 != report.result.evidence_sha256
            or verified.retained_rows_sha256 != report.result.retained_rows_sha256
        ):
            raise RuntimeError("cutover database evidence differs from the staged report")
        if not verified.already_completed and (
            verified.deleted_legacy_checkpoint_count != report.result.deleted_legacy_checkpoint_count
            or verified.deleted_legacy_blob_count != report.result.deleted_legacy_blob_count
            or verified.deleted_legacy_write_count != report.result.deleted_legacy_write_count
        ):
            raise RuntimeError("recovered cutover deletion evidence differs from the staged report")


def _publish_completed_report(
    engine: Engine,
    staged_path: Path,
    output_path: Path,
    *,
    expected_as_of: datetime,
) -> None:
    report = _read_completed_report(staged_path)
    _verify_completed_report(engine, report, expected_as_of=expected_as_of)
    staged_path.replace(output_path)
    _fsync_directory(output_path.parent)


def _execute_locked(engine: Engine, *, output_path: Path, as_of: datetime) -> int:
    staged_path = output_path.with_name(f".{output_path.name}.completed.tmp")
    if staged_path.exists():
        try:
            _publish_completed_report(engine, staged_path, output_path, expected_as_of=as_of)
        except Exception:
            return 1
        return 0

    if output_path.exists():
        try:
            existing = CheckpointCutoverRunReport.model_validate_json(output_path.read_text(encoding="utf-8"))
            if existing.scope_status == "COMPLETED":
                _verify_completed_report(engine, existing, expected_as_of=as_of)
                return 0
        except Exception:
            return 1

    in_progress = CheckpointCutoverRunReport(scope_status="IN_PROGRESS", as_of=as_of)
    try:
        _write_report(output_path, in_progress)
    except Exception:
        return 1

    staged_created = False
    try:
        with engine.begin() as connection:
            result = AgentCheckpointCutoverService(connection).run(as_of=as_of)
            completed = CheckpointCutoverRunReport(
                scope_status="COMPLETED",
                as_of=as_of,
                result=result,
            )
            staged_path = _stage_completed_report(output_path, completed)
            staged_created = True
    except AgentCheckpointCutoverError as error:
        if staged_created:
            return 1
        failed = in_progress.model_copy(
            update={
                "scope_status": "FAILED",
                "failure_code": "RELEASE_GATE_BLOCKED",
                "blockers": error.blockers,
            }
        )
        with suppress(Exception):
            _write_report(output_path, failed)
        return 2
    except Exception:
        if staged_created:
            return 1
        failed = in_progress.model_copy(
            update={
                "scope_status": "FAILED",
                "failure_code": "CUTOVER_EXECUTION_FAILED",
            }
        )
        with suppress(Exception):
            _write_report(output_path, failed)
        return 1

    try:
        _publish_completed_report(engine, staged_path, output_path, expected_as_of=as_of)
    except Exception:
        return 1
    return 0


def execute_checkpoint_cutover(
    engine: Engine,
    *,
    output_path: Path,
    as_of: datetime,
) -> int:
    """Serialize execution, stage evidence before commit, then verify and publish it."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output_path.with_name(f".{output_path.name}.lock")
    lock_existed = lock_path.exists()
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        if not lock_existed:
            _fsync_directory(lock_path.parent)
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 1
        try:
            return _execute_locked(engine, output_path=output_path, as_of=as_of)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        required=True,
        help="Fixed aware ISO timestamp, for example 2026-08-23T23:59:59+08:00.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the content-free JSON evidence report.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required acknowledgement that historical checkpoint rows may be deleted.",
    )
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("--execute is required")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        as_of = parse_business_as_of(args.as_of)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    from app.core.database import engine

    return execute_checkpoint_cutover(engine, output_path=args.output, as_of=as_of)


if __name__ == "__main__":
    raise SystemExit(main())
