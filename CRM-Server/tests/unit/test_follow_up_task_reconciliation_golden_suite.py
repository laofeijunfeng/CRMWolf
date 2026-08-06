import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.services.follow_up_task_reconciliation_golden_suite import (
    DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH,
    load_golden_cases,
    run_follow_up_task_reconciliation_golden_suite,
)

MIN_GOLDEN_CASE_COUNT = 30
LEGACY_CORE_CASE_NAMES = {
    "same_owner_completed_budget_check",
    "same_owner_delay_budget_check",
    "same_customer_unrelated_new_demo",
    "cross_owner_completion_needs_confirmation",
    "low_confidence_vague_progress_needs_confirmation",
}


def test_follow_up_task_reconciliation_golden_cases_load_from_fixture():
    cases = load_golden_cases()

    assert DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH.exists()
    assert len(cases) >= MIN_GOLDEN_CASE_COUNT
    assert cases[0].name == "same_owner_completed_budget_check"


def test_follow_up_task_reconciliation_golden_cases_cover_required_categories():
    raw_cases = json.loads(DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH.read_text(encoding="utf-8"))
    category_counts = Counter(
        case.get("category")
        for case in raw_cases
        if isinstance(case, dict) and isinstance(case.get("category"), str)
    )

    assert len(raw_cases) >= MIN_GOLDEN_CASE_COUNT
    assert set(category_counts) >= {
        "same_owner_complete",
        "same_owner_delay",
        "unrelated_new_action",
        "cross_owner_confirmation",
        "low_confidence_confirmation",
        "manual_clear_boundary",
        "delete_boundary",
        "same_owner_cancel",
        "keep_open",
    }
    assert category_counts["same_owner_complete"] >= 5
    assert category_counts["same_owner_delay"] >= 5
    assert category_counts["unrelated_new_action"] >= 4
    assert category_counts["cross_owner_confirmation"] >= 5
    assert category_counts["low_confidence_confirmation"] >= 5
    assert category_counts["manual_clear_boundary"] + category_counts["delete_boundary"] >= 3


def test_follow_up_task_reconciliation_golden_suite_passes_core_contracts():
    cases = load_golden_cases()
    summary = run_follow_up_task_reconciliation_golden_suite()

    assert summary.ok is True
    assert summary.total == len(cases)
    assert summary.total >= MIN_GOLDEN_CASE_COUNT
    assert summary.failed == 0
    assert {result.case_name for result in summary.results} >= LEGACY_CORE_CASE_NAMES


def test_follow_up_task_reconciliation_golden_script_returns_success():
    fixture_path = Path("tests/fixtures/follow_up_task_reconciliation_golden_cases.json")
    completed = subprocess.run(
        [sys.executable, "scripts/run_follow_up_task_reconciliation_eval.py", str(fixture_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert '"ok": true' in completed.stdout
    assert '"failed": 0' in completed.stdout
    assert '"metrics"' in completed.stdout
