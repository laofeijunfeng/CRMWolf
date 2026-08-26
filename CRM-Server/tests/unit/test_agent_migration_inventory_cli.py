"""Behavior tests for the reproducible Agent migration inventory command."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import BaseModel

from scripts import inventory_agent_migration_data as inventory_cli


class _Report(BaseModel):
    schema_version: str = "crm.agent.migration-inventory.v2"
    as_of: datetime
    blocking_unknowns: list[str]


def test_inventory_cli_requires_an_aware_as_of_and_normalizes_it_to_shanghai() -> None:
    assert inventory_cli.parse_as_of("2026-08-23T15:59:59+00:00") == datetime(2026, 8, 23, 23, 59, 59)

    with pytest.raises(ValueError, match="timezone"):
        inventory_cli.parse_as_of("2026-08-23T23:59:59")


def test_inventory_cli_returns_two_for_a_blocked_release_gate(monkeypatch, capsys) -> None:
    captured: dict[str, datetime] = {}

    class FakeInventory:
        def __init__(self, _engine, *, as_of: datetime) -> None:
            captured["as_of"] = as_of

        def collect(self) -> _Report:
            return _Report(as_of=captured["as_of"], blocking_unknowns=["legacy_task:active"])

    monkeypatch.setattr(inventory_cli, "AgentMigrationInventory", FakeInventory)

    exit_code = inventory_cli.main(["--as-of", "2026-08-23T23:59:59+08:00"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert captured["as_of"] == datetime(2026, 8, 23, 23, 59, 59)
    assert payload["blocking_unknowns"] == ["legacy_task:active"]


def test_inventory_cli_report_only_keeps_a_blocked_report_successful(monkeypatch) -> None:
    class FakeInventory:
        def __init__(self, _engine, *, as_of: datetime) -> None:
            self._as_of = as_of

        def collect(self) -> _Report:
            return _Report(as_of=self._as_of, blocking_unknowns=["legacy_task:active"])

    monkeypatch.setattr(inventory_cli, "AgentMigrationInventory", FakeInventory)

    assert inventory_cli.main(["--as-of", "2026-08-23T23:59:59+08:00", "--report-only"]) == 0
