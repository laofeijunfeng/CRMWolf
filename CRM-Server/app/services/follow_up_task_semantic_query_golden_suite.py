"""Golden regression suite for semantic follow-up task query contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

JsonObject = dict[str, object]
DEFAULT_SEMANTIC_QUERY_GOLDEN_CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "follow_up_task_semantic_query_golden_cases.json"
)


@dataclass(frozen=True)
class FollowUpTaskSemanticQueryTaskCase:
    public_id: str
    customer_public_id: str
    customer_name: str
    owner_id: str
    status: str
    title: str
    description: str
    due_at: str
    completed_at: str | None = None
    cancelled_at: str | None = None


@dataclass(frozen=True)
class FollowUpTaskSemanticQueryGoldenCase:
    name: str
    category: str
    query_text: str
    user_id: int
    status: str
    owner_scope: str
    tasks: tuple[FollowUpTaskSemanticQueryTaskCase, ...]
    semantic_task_public_ids: tuple[str, ...]
    expected_task_public_ids: tuple[str, ...]
    forbidden_task_public_ids: tuple[str, ...]


@dataclass(frozen=True)
class FollowUpTaskSemanticQueryGoldenResult:
    case_name: str
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class FollowUpTaskSemanticQueryGoldenSummary:
    total: int
    passed: int
    failed: int
    results: tuple[FollowUpTaskSemanticQueryGoldenResult, ...]

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "results": [
                {
                    "case_name": result.case_name,
                    "passed": result.passed,
                    "failures": list(result.failures),
                }
                for result in self.results
            ],
        }


def run_follow_up_task_semantic_query_golden_suite(
    cases_path: Path | str = DEFAULT_SEMANTIC_QUERY_GOLDEN_CASES_PATH,
) -> FollowUpTaskSemanticQueryGoldenSummary:
    cases = load_golden_cases(cases_path)
    results = tuple(_evaluate_case_contract(case) for case in cases)
    passed = sum(1 for result in results if result.passed)
    return FollowUpTaskSemanticQueryGoldenSummary(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )


def load_golden_cases(
    cases_path: Path | str = DEFAULT_SEMANTIC_QUERY_GOLDEN_CASES_PATH,
) -> list[FollowUpTaskSemanticQueryGoldenCase]:
    raw_cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ValueError("follow-up task semantic query golden cases must be a JSON array")
    return [_build_case(_json_object(raw_case)) for raw_case in raw_cases]


def _build_case(raw_case: JsonObject) -> FollowUpTaskSemanticQueryGoldenCase:
    return FollowUpTaskSemanticQueryGoldenCase(
        name=_required_text(raw_case, "name"),
        category=_required_text(raw_case, "category"),
        query_text=_required_text(raw_case, "query_text"),
        user_id=int(_required_number(raw_case, "user_id")),
        status=_required_text(raw_case, "status"),
        owner_scope=_required_text(raw_case, "owner_scope"),
        tasks=tuple(_build_task(task) for task in _json_object_list(raw_case.get("tasks"))),
        semantic_task_public_ids=tuple(_text_list(raw_case.get("semantic_task_public_ids"))),
        expected_task_public_ids=tuple(_text_list(raw_case.get("expected_task_public_ids"))),
        forbidden_task_public_ids=tuple(_text_list(raw_case.get("forbidden_task_public_ids"))),
    )


def _build_task(raw_task: JsonObject) -> FollowUpTaskSemanticQueryTaskCase:
    return FollowUpTaskSemanticQueryTaskCase(
        public_id=_required_text(raw_task, "public_id"),
        customer_public_id=_required_text(raw_task, "customer_public_id"),
        customer_name=_required_text(raw_task, "customer_name"),
        owner_id=_required_text(raw_task, "owner_id"),
        status=_required_text(raw_task, "status"),
        title=_required_text(raw_task, "title"),
        description=_required_text(raw_task, "description"),
        due_at=_required_text(raw_task, "due_at"),
        completed_at=_optional_text(raw_task.get("completed_at")),
        cancelled_at=_optional_text(raw_task.get("cancelled_at")),
    )


def _evaluate_case_contract(case: FollowUpTaskSemanticQueryGoldenCase) -> FollowUpTaskSemanticQueryGoldenResult:
    failures: list[str] = []
    task_public_ids = {task.public_id for task in case.tasks}
    if case.status not in {"open", "completed", "cancelled", "all"}:
        failures.append(f"invalid_status:{case.status}")
    if case.owner_scope not in {"mine", "customer"}:
        failures.append(f"invalid_owner_scope:{case.owner_scope}")
    for task_public_id in task_public_ids:
        if not task_public_id.startswith("fut_"):
            failures.append(f"invalid_task_public_id:{task_public_id}")
    for task_public_id in case.semantic_task_public_ids:
        if task_public_id not in task_public_ids:
            failures.append(f"semantic_candidate_unknown:{task_public_id}")
    for task_public_id in case.expected_task_public_ids:
        if task_public_id not in case.semantic_task_public_ids:
            failures.append(f"expected_not_semantic_candidate:{task_public_id}")
    for task_public_id in case.forbidden_task_public_ids:
        if task_public_id in case.expected_task_public_ids:
            failures.append(f"task_both_expected_and_forbidden:{task_public_id}")
    return FollowUpTaskSemanticQueryGoldenResult(
        case_name=case.name,
        passed=not failures,
        failures=tuple(failures),
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


def _required_number(data: JsonObject, key: str) -> int | float:
    value = data.get(key)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"missing required number field: {key}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid number field: {key}") from exc
