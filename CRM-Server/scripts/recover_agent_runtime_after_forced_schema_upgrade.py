#!/usr/bin/env python3
"""Reset unrecoverable historical Agent runtime after a forced schema upgrade.

This is an exceptional, destructive *offline-only* maintenance command. It
obtains a MySQL WRITE lock on every CRM table before inspecting or deleting any
runtime data. It deletes only legacy Agent checkpoint runtime, terminal Customer
Intelligence checkpoint runtime, and fully legacy Agent message history. It
retains adjacent workflow checkpoints and CRM business records, including
Customer Intelligence run rows.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy.engine import Connection, Engine

from app.services.agent.forced_schema_recovery import (
    FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION,
    ForcedSchemaRecoveryError,
    ForcedSchemaRecoveryResult,
    ForcedSchemaRecoveryService,
    TableRowCounts,
)

_MYSQL_LOCK_WAIT_TIMEOUT_SECONDS = 15


def _report_payload(
    *, status: str, result: ForcedSchemaRecoveryResult | None, blockers: list[str]
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION,
        "status": status,
        "blockers": blockers,
    }
    if result is not None:
        payload["result"] = result.to_dict()
    return payload


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_evidence_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    _fsync_directory(path)


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    _ensure_evidence_directory(path.parent)
    temporary_path = path.with_name(f".{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8") as report:
        os.fchmod(report.fileno(), 0o600)
        json.dump(payload, report, ensure_ascii=False, indent=2, sort_keys=True)
        report.write("\n")
        report.flush()
        os.fsync(report.fileno())
    temporary_path.replace(path)
    os.chmod(path, 0o600)
    _fsync_directory(path.parent)


def _read_completed_result(path: Path) -> ForcedSchemaRecoveryResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != FORCED_SCHEMA_RECOVERY_SCHEMA_VERSION or payload.get("status") != "COMPLETED":
        raise ForcedSchemaRecoveryError("recovery:completed_evidence_invalid")
    raw_result = payload.get("result")
    if not isinstance(raw_result, dict):
        raise ForcedSchemaRecoveryError("recovery:completed_evidence_invalid")
    try:
        result = ForcedSchemaRecoveryResult(
            schema_version=str(raw_result["schema_version"]),
            already_completed=raw_result["already_completed"],
            deleted_agent_message_count=_nonnegative_int(raw_result["deleted_agent_message_count"]),
            deleted_legacy_checkpoint_rows=_table_row_counts(raw_result["deleted_legacy_checkpoint_rows"]),
            deleted_customer_intelligence_checkpoint_rows=_table_row_counts(
                raw_result["deleted_customer_intelligence_checkpoint_rows"]
            ),
            retained_adjacent_checkpoint_rows=_table_row_counts(raw_result["retained_adjacent_checkpoint_rows"]),
            retained_adjacent_rows_sha256=str(raw_result["retained_adjacent_rows_sha256"]),
            evidence_sha256=str(raw_result["evidence_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ForcedSchemaRecoveryError("recovery:completed_evidence_invalid") from error
    if not isinstance(result.already_completed, bool):
        raise ForcedSchemaRecoveryError("recovery:completed_evidence_invalid")
    return result


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected non-negative integer")
    return value


def _table_row_counts(value: object) -> TableRowCounts:
    if not isinstance(value, dict):
        raise TypeError("expected row count object")
    return TableRowCounts(
        checkpoints=_nonnegative_int(value["checkpoints"]),
        blobs=_nonnegative_int(value["blobs"]),
        writes=_nonnegative_int(value["writes"]),
    )


def _verify_completed_report(engine: Engine, path: Path) -> None:
    result = _read_completed_result(path)
    with engine.connect() as connection:
        ForcedSchemaRecoveryService(connection).verify_committed_post_state(result)


def _publish_completed_report(engine: Engine, staged_path: Path, output_path: Path) -> None:
    _verify_completed_report(engine, staged_path)
    _ensure_evidence_directory(output_path.parent)
    staged_path.replace(output_path)
    os.chmod(output_path, 0o600)
    _fsync_directory(output_path.parent)


def _journal_exists(engine: Engine) -> bool:
    with engine.connect() as connection:
        return ForcedSchemaRecoveryService(connection).has_completed_journal()


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _mysql_lock_spec(connection: Connection) -> str:
    table_names = sorted(
        table_name for table_name in inspect(connection).get_table_names() if table_name.startswith("crm_")
    )
    if not table_names:
        raise ForcedSchemaRecoveryError("recovery:mysql_crm_tables_missing")
    return ", ".join(f"{_quote_identifier(table_name)} WRITE" for table_name in table_names)


@contextmanager
def _locked_recovery_connection(engine: Engine) -> Iterator[Connection]:
    """Yield a transaction that prevents concurrent CRM writers during recovery.

    Production uses MySQL. `LOCK TABLES ... WRITE` is intentionally broad: it
    blocks every CRM-table writer from creating target runtime or new-format
    messages between the fail-closed inventory and the destructive delete. The
    SQLite branch is solely for hermetic unit-test engines; production command
    invocations must use MySQL.
    """
    with engine.connect() as connection:
        if connection.dialect.name != "mysql":
            with connection.begin():
                yield connection
            return

        lock_spec = _mysql_lock_spec(connection)
        connection.commit()
        locked = False
        try:
            connection.execute(text(f"SET SESSION lock_wait_timeout = {_MYSQL_LOCK_WAIT_TIMEOUT_SECONDS}"))
            connection.execute(text("SET autocommit = 0"))
            connection.execute(text(f"LOCK TABLES {lock_spec}"))
            locked = True
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            try:
                if locked:
                    connection.execute(text("UNLOCK TABLES"))
            finally:
                connection.execute(text("SET autocommit = 1"))


def _remove_stale_stage_if_uncommitted(engine: Engine, staged_path: Path) -> bool:
    try:
        journal_exists = _journal_exists(engine)
    except Exception:
        return False
    if journal_exists:
        return False
    try:
        staged_path.unlink()
        _fsync_directory(staged_path.parent)
    except OSError:
        return False
    return True


def _execute_locked(engine: Engine, *, output_path: Path) -> int:
    staged_path = output_path.with_name(f".{output_path.name}.completed.tmp")
    if staged_path.exists():
        try:
            _publish_completed_report(engine, staged_path, output_path)
            return 0
        except Exception:
            if not _remove_stale_stage_if_uncommitted(engine, staged_path):
                return 1

    if output_path.exists():
        try:
            _verify_completed_report(engine, output_path)
            return 0
        except Exception:
            try:
                if _journal_exists(engine):
                    return 1
            except Exception:
                return 1

    try:
        _write_payload(output_path, _report_payload(status="IN_PROGRESS", result=None, blockers=[]))
    except OSError:
        return 1

    staged_created = False
    try:
        with _locked_recovery_connection(engine) as connection:
            service = ForcedSchemaRecoveryService(connection)
            service.run(
                stage_completed_result=lambda result: _write_payload(
                    staged_path,
                    _report_payload(status="COMPLETED", result=result, blockers=[]),
                )
            )
            staged_created = True
    except ForcedSchemaRecoveryError as error:
        if staged_created:
            return 1
        with suppress(OSError):
            _write_payload(output_path, _report_payload(status="FAILED", result=None, blockers=error.blockers))
        return 2
    except Exception:
        if staged_created:
            return 1
        with suppress(OSError):
            _write_payload(
                output_path,
                _report_payload(status="FAILED", result=None, blockers=["recovery:execution_failed"]),
            )
        return 1

    try:
        _publish_completed_report(engine, staged_path, output_path)
    except Exception:
        return 1
    return 0


def execute_forced_schema_recovery(engine: Engine, *, output_path: Path) -> int:
    """Serialize evidence writes, stage before commit, then verify and publish."""
    _ensure_evidence_directory(output_path.parent)
    lock_path = output_path.with_name(f".{output_path.name}.lock")
    lock_existed = lock_path.exists()
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        os.fchmod(lock_handle.fileno(), 0o600)
        if not lock_existed:
            _fsync_directory(lock_path.parent)
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 1
        try:
            return _execute_locked(engine, output_path=output_path)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Content-free JSON evidence destination.")
    parser.add_argument("--execute", action="store_true", help="Required acknowledgement that data will be deleted.")
    parser.add_argument(
        "--offline-confirmed",
        action="store_true",
        help="Confirm that every application/background writer is stopped before this command runs.",
    )
    parser.add_argument(
        "--accept-legacy-agent-runtime-loss",
        action="store_true",
        help="Acknowledge deletion of legacy Agent checkpoint runtime.",
    )
    parser.add_argument(
        "--accept-agent-message-history-loss",
        action="store_true",
        help="Acknowledge deletion of unmigratable legacy Agent message history.",
    )
    parser.add_argument(
        "--reset-terminal-customer-intelligence-checkpoints",
        action="store_true",
        help="Acknowledge reset of Customer Intelligence checkpoints only when all runs are terminal.",
    )
    args = parser.parse_args(argv)
    required_flags = (
        "execute",
        "offline_confirmed",
        "accept_legacy_agent_runtime_loss",
        "accept_agent_message_history_loss",
        "reset_terminal_customer_intelligence_checkpoints",
    )
    missing = [f"--{flag.replace('_', '-')}" for flag in required_flags if not getattr(args, flag)]
    if missing:
        parser.error(f"all explicit acknowledgements are required: {', '.join(missing)}")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    from app.core.database import engine

    return execute_forced_schema_recovery(engine, output_path=args.output)


if __name__ == "__main__":
    raise SystemExit(main())
