#!/usr/bin/env python3
"""Generate or verify the reviewed CRM Agent JSON Schema bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.agent.contract_schema import build_agent_contract_schema_bundle

DEFAULT_OUTPUT = (
    Path(__file__).parents[1]
    / "tests"
    / "fixtures"
    / "agent_contracts"
    / "crm_agent_contracts.schema.json"
)


def _serialized_bundle() -> str:
    return json.dumps(build_agent_contract_schema_bundle(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed schema does not match generated output",
    )
    args = parser.parse_args()

    expected = _serialized_bundle()
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
            print(f"Agent contract schema is stale: {args.output}")
            return 1
        print(f"Agent contract schema is current: {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    print(f"Wrote Agent contract schema: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
