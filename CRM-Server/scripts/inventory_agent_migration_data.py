"""Export reproducible, content-free evidence before the Agent cutover."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.database import engine
from app.services.agent.migration_inventory import AgentMigrationInventory
from app.services.agent.migration_time import parse_business_as_of

parse_as_of = parse_business_as_of


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a content-free CRM Agent migration inventory as JSON.",
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="Fixed aware ISO timestamp, for example 2026-08-23T23:59:59+08:00.",
    )
    parser.add_argument("--output", type=Path, help="Output file. Defaults to stdout.")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Return exit code 0 even when the release gate is blocked.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        as_of = parse_as_of(args.as_of)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    report = AgentMigrationInventory(engine, as_of=as_of).collect()
    payload = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    if report.blocking_unknowns and not args.report_only:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
