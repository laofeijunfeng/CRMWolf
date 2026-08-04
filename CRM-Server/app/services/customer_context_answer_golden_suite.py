"""Golden regression suite for customer context answer contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.customer_context_answer_evaluation_service import (
    CustomerContextAnswerEvaluationCase,
    CustomerContextAnswerEvaluationSummary,
    customer_context_answer_evaluation_service,
)
from app.services.customer_context_answer_service import CustomerContextAnswerService

JsonObject = dict[str, object]
DEFAULT_GOLDEN_CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "customer_context_answer_golden_cases.json"
)


def run_customer_context_answer_golden_suite(
    cases_path: Path | str = DEFAULT_GOLDEN_CASES_PATH,
) -> CustomerContextAnswerEvaluationSummary:
    """Run deterministic CRM Agent answer contract checks."""

    return customer_context_answer_evaluation_service.evaluate_many(load_golden_cases(cases_path))


def load_golden_cases(
    cases_path: Path | str = DEFAULT_GOLDEN_CASES_PATH,
) -> list[CustomerContextAnswerEvaluationCase]:
    raw_cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ValueError("customer context answer golden cases must be a JSON array")
    return [_build_case(_json_object(raw_case)) for raw_case in raw_cases]


def _build_case(raw_case: JsonObject) -> CustomerContextAnswerEvaluationCase:
    execution = _required_text(raw_case, "execution")
    if execution == "fallback_answer":
        result = CustomerContextAnswerService.fallback_answer(
            question=_required_text(raw_case, "question"),
            customer_context=_json_object(raw_case.get("customer_context")),
            customer_memory=_json_object(raw_case.get("customer_memory")),
        )
    elif execution == "metadata_cleanup":
        result = CustomerContextAnswerService._with_answer_metadata(
            CustomerContextAnswerResult.model_validate(_json_object(raw_case.get("model_result"))),
            _json_object(raw_case.get("customer_context")),
        )
    else:
        raise ValueError(f"unsupported golden case execution: {execution}")

    expected = _json_object(raw_case.get("expected"))
    return CustomerContextAnswerEvaluationCase(
        name=_required_text(raw_case, "name"),
        result=result,
        retrieval_status=_optional_text(expected.get("retrieval_status")),
        allowed_answer_modes=set(_text_list(expected.get("allowed_answer_modes"))),
        require_citations=bool(expected.get("require_citations")),
        forbid_citations=bool(expected.get("forbid_citations")),
        min_confidence=_optional_float(expected.get("min_confidence")),
        required_answer_terms=tuple(_text_list(expected.get("required_answer_terms"))),
        required_missing_context_terms=tuple(_text_list(expected.get("required_missing_context_terms"))),
    )


def _json_object(value: Any) -> JsonObject:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    raise ValueError("expected JSON object")


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
