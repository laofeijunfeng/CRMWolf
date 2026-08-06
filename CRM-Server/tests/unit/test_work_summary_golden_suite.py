import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.services.work_summary_golden_suite import (
    DEFAULT_WORK_SUMMARY_GOLDEN_CASES_PATH,
    load_golden_cases,
    run_work_summary_golden_suite,
)

MIN_WORK_SUMMARY_GOLDEN_CASE_COUNT = 6


def test_work_summary_golden_cases_load_from_fixture():
    cases = load_golden_cases()

    assert DEFAULT_WORK_SUMMARY_GOLDEN_CASES_PATH.exists()
    assert len(cases) >= MIN_WORK_SUMMARY_GOLDEN_CASE_COUNT
    assert cases[0].name == "grounded_week_summary_mixed_sources"


def test_work_summary_golden_cases_cover_required_categories():
    raw_cases = json.loads(DEFAULT_WORK_SUMMARY_GOLDEN_CASES_PATH.read_text(encoding="utf-8"))
    category_counts = Counter(
        case.get("category")
        for case in raw_cases
        if isinstance(case, dict) and isinstance(case.get("category"), str)
    )

    assert set(category_counts) >= {
        "mixed_sources",
        "category_boundary",
        "business_progress",
        "pagination",
        "owner_scope",
        "human_correction",
    }


def test_work_summary_golden_suite_passes_core_contracts():
    cases = load_golden_cases()
    summary = run_work_summary_golden_suite()
    metrics = summary.metrics.to_dict()

    assert summary.ok is True
    assert summary.total == len(cases)
    assert summary.total >= MIN_WORK_SUMMARY_GOLDEN_CASE_COUNT
    assert summary.failed == 0
    assert metrics["fact_recall"]["rate"] == 1.0
    assert metrics["citation_completeness"]["rate"] == 1.0
    assert metrics["hallucination_rate"]["rate"] == 0.0
    assert metrics["owner_attribution_errors"]["rate"] == 0.0
    assert metrics["time_window_errors"]["rate"] == 0.0
    assert metrics["classification_errors"]["rate"] == 0.0
    assert metrics["correction_actionability"]["rate"] == 1.0


def test_work_summary_golden_script_returns_success():
    fixture_path = Path("tests/fixtures/work_summary_golden_cases.json")
    completed = subprocess.run(
        [sys.executable, "scripts/run_work_summary_eval.py", str(fixture_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert '"ok": true' in completed.stdout
    assert '"failed": 0' in completed.stdout
    assert '"fact_recall"' in completed.stdout
