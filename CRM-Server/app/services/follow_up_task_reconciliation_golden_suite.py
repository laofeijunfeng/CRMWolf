"""Golden regression suite for follow-up task reconciliation contracts."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.follow_up_task_reconciliation_evaluation_service import (
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationEvaluationCase,
    FollowUpTaskReconciliationEvaluationSummary,
    follow_up_task_reconciliation_evaluation_service,
)

JsonObject = dict[str, object]
DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "follow_up_task_reconciliation_golden_cases.json"
)


def run_follow_up_task_reconciliation_golden_suite(
    cases_path: Path | str = DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH,
) -> FollowUpTaskReconciliationEvaluationSummary:
    """Run deterministic follow-up task reconciliation contract checks."""

    return follow_up_task_reconciliation_evaluation_service.evaluate_many(load_golden_cases(cases_path))


def load_golden_cases(
    cases_path: Path | str = DEFAULT_RECONCILIATION_GOLDEN_CASES_PATH,
) -> list[FollowUpTaskReconciliationEvaluationCase]:
    raw_cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ValueError("follow-up task reconciliation golden cases must be a JSON array")
    return [_build_case(_json_object(raw_case)) for raw_case in raw_cases]


def _build_case(raw_case: JsonObject) -> FollowUpTaskReconciliationEvaluationCase:
    execution = _required_text(raw_case, "execution")
    if execution != "static_decision":
        raise ValueError(f"unsupported reconciliation golden case execution: {execution}")

    input_payload = _json_object(raw_case.get("input"))
    activity = _json_object(input_payload.get("activity"))
    task_owner_by_public_id = {
        _required_text(task, "public_id"): _required_text(task, "owner_id")
        for task in _json_object_list(input_payload.get("open_tasks"))
    }
    expected = _json_object(raw_case.get("expected"))
    return FollowUpTaskReconciliationEvaluationCase(
        name=_required_text(raw_case, "name"),
        activity_owner_id=_required_text(activity, "owner_id"),
        task_owner_by_public_id=task_owner_by_public_id,
        result=_build_decision(_json_object(raw_case.get("result"))),
        expected_decision=_optional_text(expected.get("decision")),
        allowed_decisions=set(_text_list(expected.get("allowed_decisions"))),
        expected_task_public_id=_optional_text(expected.get("task_public_id")),
        required_candidate_public_ids=tuple(_text_list(expected.get("required_candidate_public_ids"))),
        forbidden_candidate_public_ids=tuple(_text_list(expected.get("forbidden_candidate_public_ids"))),
        min_confidence=_optional_float(expected.get("min_confidence")),
        max_confidence=_optional_float(expected.get("max_confidence")),
        require_confirmation=bool(expected.get("require_confirmation")),
        forbid_confirmation=bool(expected.get("forbid_confirmation")),
        required_forbid_auto_reasons=tuple(_text_list(expected.get("required_forbid_auto_reasons"))),
        required_evidence_terms=tuple(_text_list(expected.get("required_evidence_terms"))),
        forbid_state_mutation=bool(expected.get("forbid_state_mutation", True)),
        require_public_ids=bool(expected.get("require_public_ids", True)),
        allow_cross_owner_auto_transition=bool(expected.get("allow_cross_owner_auto_transition")),
    )


def _build_decision(raw_result: JsonObject) -> FollowUpTaskReconciliationDecision:
    return FollowUpTaskReconciliationDecision(
        decision=_required_text(raw_result, "decision"),
        task_public_id=_optional_text(raw_result.get("task_public_id")),
        candidate_public_ids=tuple(_text_list(raw_result.get("candidate_public_ids"))),
        confidence=_required_float(raw_result, "confidence"),
        needs_confirmation=bool(raw_result.get("needs_confirmation")),
        proposed_due_at=_optional_text(raw_result.get("proposed_due_at")),
        forbid_auto_reasons=tuple(_text_list(raw_result.get("forbid_auto_reasons"))),
        evidence_terms=tuple(_text_list(raw_result.get("evidence_terms"))),
        state_mutation_requested=bool(raw_result.get("state_mutation_requested")),
    )


def _json_object(value: object) -> JsonObject:
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


def _required_float(data: JsonObject, key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"missing required float field: {key}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid float field: {key}") from exc


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
