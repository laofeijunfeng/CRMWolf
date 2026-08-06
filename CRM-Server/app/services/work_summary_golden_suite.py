"""Golden regression suite for work summary grounding contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.agent.schemas import WorkSummaryNarrativeResult
from app.services.work_summary_evaluation_service import (
    WorkSummaryEvaluationCase,
    WorkSummaryEvaluationSummary,
    WorkSummaryHumanCorrection,
    work_summary_evaluation_service,
)

JsonObject = dict[str, object]
DEFAULT_WORK_SUMMARY_GOLDEN_CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "work_summary_golden_cases.json"
)


def run_work_summary_golden_suite(
    cases_path: Path | str = DEFAULT_WORK_SUMMARY_GOLDEN_CASES_PATH,
) -> WorkSummaryEvaluationSummary:
    """Run deterministic work summary fact and narrative contract checks."""

    return work_summary_evaluation_service.evaluate_many(load_golden_cases(cases_path))


def load_golden_cases(
    cases_path: Path | str = DEFAULT_WORK_SUMMARY_GOLDEN_CASES_PATH,
) -> list[WorkSummaryEvaluationCase]:
    raw_cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ValueError("work summary golden cases must be a JSON array")
    return [_build_case(_json_object(raw_case)) for raw_case in raw_cases]


def _build_case(raw_case: JsonObject) -> WorkSummaryEvaluationCase:
    execution = _required_text(raw_case, "execution")
    if execution != "static_narrative":
        raise ValueError(f"unsupported work summary golden case execution: {execution}")

    expected = _json_object(raw_case.get("expected"))
    return WorkSummaryEvaluationCase(
        name=_required_text(raw_case, "name"),
        work_facts=_json_object(raw_case.get("work_facts")),
        result=WorkSummaryNarrativeResult.model_validate(_json_object(raw_case.get("result"))),
        required_fact_ids=tuple(_text_list(expected.get("required_fact_ids"))),
        forbidden_fact_ids=tuple(_text_list(expected.get("forbidden_fact_ids"))),
        required_fact_types=tuple(_text_list(expected.get("required_fact_types"))),
        expected_source_total_counts={
            key: int(value)
            for key, value in _json_object(expected.get("source_total_counts")).items()
            if isinstance(key, str) and isinstance(value, int)
        },
        expected_owner_id=_optional_text(expected.get("owner_id")),
        min_confidence=_optional_float(expected.get("min_confidence")),
        require_truncated_disclosure=bool(expected.get("require_truncated_disclosure")),
        required_answer_terms=tuple(_text_list(expected.get("required_answer_terms"))),
        human_corrections=tuple(
            _build_correction(correction)
            for correction in _json_object_list(raw_case.get("human_corrections"))
        ),
    )


def _build_correction(raw_correction: JsonObject) -> WorkSummaryHumanCorrection:
    return WorkSummaryHumanCorrection(
        correction_type=_required_text(raw_correction, "correction_type"),
        note=_required_text(raw_correction, "note"),
        target_fact_id=_optional_text(raw_correction.get("target_fact_id")),
        corrected_category=_optional_text(raw_correction.get("corrected_category")),
        replacement_text=_optional_text(raw_correction.get("replacement_text")),
        feedback_source=_optional_text(raw_correction.get("feedback_source")) or "human_review",
    )


def _json_object(value: Any) -> JsonObject:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    raise ValueError("expected JSON object")


def _json_object_list(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [_json_object(item) for item in value]


def _required_text(data: JsonObject, key: str) -> str:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"missing required text field: {key}")


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
