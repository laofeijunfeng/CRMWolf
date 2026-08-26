"""Behavior tests for the single-version checkpoint cutover command."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime

from app.services.agent.checkpoint_cutover import AgentCheckpointCutoverError, AgentCheckpointCutoverResult
from scripts import cutover_agent_checkpoints as cutover_cli

AS_OF = datetime(2026, 8, 23, 23, 59, 59)


def _result(*, already_completed: bool) -> AgentCheckpointCutoverResult:
    return AgentCheckpointCutoverResult(
        already_completed=already_completed,
        deleted_legacy_checkpoint_count=2 if not already_completed else 0,
        deleted_legacy_blob_count=3 if not already_completed else 0,
        deleted_legacy_write_count=4 if not already_completed else 0,
        target_root_checkpoint_count=1,
        target_workflow_checkpoint_count=0,
        retained_customer_intelligence_checkpoint_count=1,
        retained_adjacent_workflow_checkpoint_count=1,
        retained_rows_sha256="a" * 64,
        evidence_sha256="b" * 64,
    )


class _Engine:
    @contextmanager
    def begin(self):
        yield object()

    @contextmanager
    def connect(self):
        yield object()


def test_cutover_cli_stages_then_publishes_verified_completed_evidence(monkeypatch, tmp_path) -> None:
    calls = iter([_result(already_completed=False), _result(already_completed=True)])

    class FakeService:
        def __init__(self, _connection) -> None:
            pass

        def run(self, *, as_of: datetime) -> AgentCheckpointCutoverResult:
            assert as_of == AS_OF
            return next(calls)

    monkeypatch.setattr(cutover_cli, "AgentCheckpointCutoverService", FakeService)
    output = tmp_path / "cutover.json"

    exit_code = cutover_cli.execute_checkpoint_cutover(
        _Engine(),
        output_path=output,
        as_of=AS_OF,
    )
    payload = json.loads(output.read_text())

    assert exit_code == 0
    assert payload["scope_status"] == "COMPLETED"
    assert payload["result"]["deleted_legacy_checkpoint_count"] == 2
    assert payload["result"]["evidence_sha256"] == "b" * 64
    assert not output.with_name(f".{output.name}.completed.tmp").exists()


def test_cutover_cli_records_stable_blockers_without_publishing_completion(monkeypatch, tmp_path) -> None:
    class FakeService:
        def __init__(self, _connection) -> None:
            pass

        def run(self, *, as_of: datetime) -> AgentCheckpointCutoverResult:
            raise AgentCheckpointCutoverError({"legacy_task:active", "customer_intelligence:live_lease"})

    monkeypatch.setattr(cutover_cli, "AgentCheckpointCutoverService", FakeService)
    output = tmp_path / "cutover.json"

    exit_code = cutover_cli.execute_checkpoint_cutover(
        _Engine(),
        output_path=output,
        as_of=AS_OF,
    )
    payload = json.loads(output.read_text())

    assert exit_code == 2
    assert payload["scope_status"] == "FAILED"
    assert payload["failure_code"] == "RELEASE_GATE_BLOCKED"
    assert payload["blockers"] == [
        "customer_intelligence:live_lease",
        "legacy_task:active",
    ]


def test_cutover_cli_recovers_a_staged_report_when_the_original_transaction_rolled_back(
    monkeypatch,
    tmp_path,
) -> None:
    class FakeService:
        def __init__(self, _connection) -> None:
            pass

        def run(self, *, as_of: datetime) -> AgentCheckpointCutoverResult:
            assert as_of == AS_OF
            return _result(already_completed=False)

    monkeypatch.setattr(cutover_cli, "AgentCheckpointCutoverService", FakeService)
    output = tmp_path / "cutover.json"
    staged = output.with_name(f".{output.name}.completed.tmp")
    staged.write_text(
        cutover_cli._report_payload(
            cutover_cli.CheckpointCutoverRunReport(
                scope_status="COMPLETED",
                as_of=AS_OF,
                result=_result(already_completed=False),
            )
        )
    )

    exit_code = cutover_cli.execute_checkpoint_cutover(
        _Engine(),
        output_path=output,
        as_of=AS_OF,
    )

    assert exit_code == 0
    assert json.loads(output.read_text())["scope_status"] == "COMPLETED"
    assert not staged.exists()


def test_cutover_cli_rejects_a_staged_report_from_a_different_business_cutoff(
    monkeypatch,
    tmp_path,
) -> None:
    service_calls: list[object] = []

    class UnexpectedService:
        def __init__(self, connection) -> None:
            service_calls.append(connection)

        def run(self, *, as_of: datetime) -> AgentCheckpointCutoverResult:
            raise AssertionError(f"cutover must not run for mismatched cutoff {as_of}")

    monkeypatch.setattr(cutover_cli, "AgentCheckpointCutoverService", UnexpectedService)
    output = tmp_path / "cutover.json"
    staged = output.with_name(f".{output.name}.completed.tmp")
    staged.write_text(
        cutover_cli._report_payload(
            cutover_cli.CheckpointCutoverRunReport(
                scope_status="COMPLETED",
                as_of=datetime(2026, 8, 23, 23, 59, 58),
                result=_result(already_completed=False),
            )
        )
    )

    exit_code = cutover_cli.execute_checkpoint_cutover(
        _Engine(),
        output_path=output,
        as_of=AS_OF,
    )

    assert exit_code == 1
    assert service_calls == []
    assert staged.exists()
    assert not output.exists()
