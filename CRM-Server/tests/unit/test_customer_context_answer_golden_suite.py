import subprocess
import sys
from pathlib import Path

from app.services.customer_context_answer_golden_suite import (
    DEFAULT_GOLDEN_CASES_PATH,
    load_golden_cases,
    run_customer_context_answer_golden_suite,
)


def test_customer_context_answer_golden_cases_load_from_fixture():
    cases = load_golden_cases()

    assert DEFAULT_GOLDEN_CASES_PATH.exists()
    assert len(cases) == 4
    assert cases[0].name == "grounded_customer_summary"


def test_customer_context_answer_golden_suite_passes_core_contracts():
    summary = run_customer_context_answer_golden_suite()

    assert summary.ok is True
    assert summary.total == 4
    assert summary.failed == 0
    assert {result.case_name for result in summary.results} == {
        "grounded_customer_summary",
        "low_confidence_fallback",
        "embedding_unavailable_profile_degraded",
        "hallucinated_citation_downgraded",
    }


def test_customer_context_answer_golden_script_returns_success():
    fixture_path = Path("tests/fixtures/customer_context_answer_golden_cases.json")
    completed = subprocess.run(
        [sys.executable, "scripts/run_customer_context_answer_eval.py", str(fixture_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert '"ok": true' in completed.stdout
    assert '"failed": 0' in completed.stdout
