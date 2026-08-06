"""Run deterministic follow-up task reconciliation golden checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.crud.sales_commitment import follow_up_task_reconciliation_evaluation_run_crud  # noqa: E402
from app.services.follow_up_task_reconciliation_golden_suite import (  # noqa: E402
    DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH,
    run_follow_up_task_reconciliation_golden_suite,
)
from app.utils.time import business_now  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic follow-up task reconciliation golden checks.")
    parser.add_argument("cases_path", nargs="?", help="Golden cases JSON path")
    parser.add_argument("--persist", action="store_true", help="Persist an append-only evaluation run row")
    parser.add_argument("--team-id", type=int, default=None, help="Optional team ID for team-specific evaluation runs")
    parser.add_argument(
        "--suite-name",
        default="follow_up_task_reconciliation_golden",
        help="Evaluation suite name",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases_path) if args.cases_path else DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH
    started_at = business_now()
    started_perf = time.perf_counter()
    summary = (
        run_follow_up_task_reconciliation_golden_suite(cases_path)
        if cases_path is not None
        else run_follow_up_task_reconciliation_golden_suite()
    )
    duration_ms = int((time.perf_counter() - started_perf) * 1000)
    payload = summary.to_dict()

    if args.persist:
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            run = follow_up_task_reconciliation_evaluation_run_crud.record_summary(
                db,
                team_id=args.team_id,
                suite_name=args.suite_name,
                fixture_path=str(cases_path),
                fixture_hash=_sha256_file(cases_path),
                summary=summary,
                duration_ms=duration_ms,
                started_at=started_at,
            )
            payload["evaluation_run_id"] = run.public_id
        finally:
            db.close()

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary.ok else 1


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
