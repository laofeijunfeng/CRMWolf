"""Run deterministic customer context answer golden checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.customer_context_answer_golden_suite import (  # noqa: E402
    run_customer_context_answer_golden_suite,
)


def main() -> int:
    cases_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    summary = (
        run_customer_context_answer_golden_suite(cases_path)
        if cases_path is not None
        else run_customer_context_answer_golden_suite()
    )
    payload = {
        "ok": summary.ok,
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "results": [
            {
                "case_name": result.case_name,
                "passed": result.passed,
                "failures": result.failures,
            }
            for result in summary.results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
