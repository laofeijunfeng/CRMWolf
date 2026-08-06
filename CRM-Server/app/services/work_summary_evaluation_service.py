"""Deterministic evaluation helpers for work summary facts and narratives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.agent.schemas import WorkSummaryNarrativeResult

WORK_SUMMARY_FACT_CATEGORIES = {
    "completed_follow_up_task": "completed_work",
    "customer_activity": "process_record",
}
WORK_SUMMARY_CORRECTION_TYPES = {
    "missing_fact",
    "remove_fact",
    "reclassify_item",
    "rewrite_summary",
    "time_window_fix",
    "owner_scope_fix",
    "citation_fix",
}
WORK_SUMMARY_CATEGORIES = {"completed_work", "process_record", "business_progress"}
DEFAULT_FORBIDDEN_WORK_SUMMARY_TOKENS = (
    "source_table",
    "source_key",
    "source_activity_id",
    "customer_id",
    "opportunity_id",
    "contract_id",
    "payment_plan_id",
    "payment_record_id",
    "invoice_application_id",
    "license_application_id",
)


@dataclass(frozen=True)
class WorkSummaryHumanCorrection:
    """A structured human correction that can become a future regression case."""

    correction_type: str
    note: str
    target_fact_id: str | None = None
    corrected_category: str | None = None
    replacement_text: str | None = None
    feedback_source: str = "human_review"


@dataclass(frozen=True)
class WorkSummaryEvaluationCase:
    """A stable regression case for work summary grounding behavior."""

    name: str
    work_facts: dict[str, Any]
    result: WorkSummaryNarrativeResult
    required_fact_ids: tuple[str, ...] = ()
    forbidden_fact_ids: tuple[str, ...] = ()
    required_fact_types: tuple[str, ...] = ()
    expected_source_total_counts: dict[str, int] = field(default_factory=dict)
    expected_owner_id: str | None = None
    min_confidence: float | None = None
    require_truncated_disclosure: bool = False
    required_answer_terms: tuple[str, ...] = ()
    forbidden_answer_tokens: tuple[str, ...] = DEFAULT_FORBIDDEN_WORK_SUMMARY_TOKENS
    human_corrections: tuple[WorkSummaryHumanCorrection, ...] = ()


@dataclass(frozen=True)
class WorkSummaryEvaluationResult:
    case_name: str
    passed: bool
    failures: list[str]


@dataclass(frozen=True)
class WorkSummaryEvaluationMetric:
    count: int
    denominator: int
    case_names: tuple[str, ...] = ()

    @property
    def rate(self) -> float:
        if self.denominator == 0:
            return 0.0
        return round(self.count / self.denominator, 4)

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "denominator": self.denominator,
            "rate": self.rate,
            "case_names": list(self.case_names),
        }


@dataclass(frozen=True)
class WorkSummaryAccuracyMetrics:
    fact_recall: WorkSummaryEvaluationMetric
    citation_completeness: WorkSummaryEvaluationMetric
    hallucination_rate: WorkSummaryEvaluationMetric
    owner_attribution_errors: WorkSummaryEvaluationMetric
    time_window_errors: WorkSummaryEvaluationMetric
    classification_errors: WorkSummaryEvaluationMetric
    correction_actionability: WorkSummaryEvaluationMetric

    def to_dict(self) -> dict[str, object]:
        return {
            "fact_recall": self.fact_recall.to_dict(),
            "citation_completeness": self.citation_completeness.to_dict(),
            "hallucination_rate": self.hallucination_rate.to_dict(),
            "owner_attribution_errors": self.owner_attribution_errors.to_dict(),
            "time_window_errors": self.time_window_errors.to_dict(),
            "classification_errors": self.classification_errors.to_dict(),
            "correction_actionability": self.correction_actionability.to_dict(),
        }


@dataclass(frozen=True)
class WorkSummaryEvaluationSummary:
    total: int
    passed: int
    failed: int
    results: list[WorkSummaryEvaluationResult]
    metrics: WorkSummaryAccuracyMetrics

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "metrics": self.metrics.to_dict(),
            "results": [
                {
                    "case_name": result.case_name,
                    "passed": result.passed,
                    "failures": result.failures,
                }
                for result in self.results
            ],
        }


@dataclass(frozen=True)
class WorkSummaryEvaluationService:
    """Evaluates work summary quality without calling an LLM or mutating business facts."""

    def evaluate_case(self, case: WorkSummaryEvaluationCase) -> WorkSummaryEvaluationResult:
        failures: list[str] = []
        facts_by_id = _facts_by_id(case.work_facts)
        referenced_fact_ids = _referenced_fact_ids(case.result)
        citations_by_id = _citations_by_id(case.result)

        for fact_id in case.required_fact_ids:
            if fact_id not in referenced_fact_ids:
                failures.append(f"fact_required_missing:{fact_id}")
        for fact_id in case.forbidden_fact_ids:
            if fact_id in referenced_fact_ids or fact_id in citations_by_id:
                failures.append(f"fact_forbidden_referenced:{fact_id}")
        for fact_id in referenced_fact_ids:
            if fact_id not in facts_by_id:
                failures.append(f"hallucinated_fact_ref:{fact_id}")
        for fact_id in citations_by_id:
            if fact_id not in facts_by_id:
                failures.append(f"citation_unknown:{fact_id}")
        for fact_id in referenced_fact_ids:
            if fact_id in facts_by_id and fact_id not in citations_by_id:
                failures.append(f"citation_missing:{fact_id}")

        failures.extend(self._fact_type_failures(case, facts_by_id))
        failures.extend(self._source_count_failures(case))
        failures.extend(self._owner_failures(case, facts_by_id))
        failures.extend(self._time_window_failures(case, facts_by_id))
        failures.extend(self._classification_failures(case, facts_by_id))
        failures.extend(self._truncation_failures(case))
        failures.extend(self._answer_failures(case))
        failures.extend(self._correction_failures(case, facts_by_id))

        return WorkSummaryEvaluationResult(
            case_name=case.name,
            passed=not failures,
            failures=failures,
        )

    def evaluate_many(self, cases: list[WorkSummaryEvaluationCase]) -> WorkSummaryEvaluationSummary:
        results = [self.evaluate_case(case) for case in cases]
        passed = sum(1 for result in results if result.passed)
        return WorkSummaryEvaluationSummary(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=results,
            metrics=self._metrics(cases),
        )

    def _fact_type_failures(
        self,
        case: WorkSummaryEvaluationCase,
        facts_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        fact_types = {str(fact.get("fact_type") or "") for fact in facts_by_id.values()}
        return [f"fact_type_missing:{fact_type}" for fact_type in case.required_fact_types if fact_type not in fact_types]

    def _source_count_failures(self, case: WorkSummaryEvaluationCase) -> list[str]:
        source_total_counts = case.work_facts.get("source_total_counts")
        if not isinstance(source_total_counts, dict):
            source_total_counts = {}
        failures: list[str] = []
        for fact_type, expected_count in case.expected_source_total_counts.items():
            actual_count = source_total_counts.get(fact_type)
            if actual_count != expected_count:
                failures.append(f"source_total_count_unexpected:{fact_type}:{actual_count}")
        return failures

    def _owner_failures(
        self,
        case: WorkSummaryEvaluationCase,
        facts_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        if case.expected_owner_id is None:
            return []
        failures: list[str] = []
        for fact_id, fact in facts_by_id.items():
            attribution = fact.get("attribution") if isinstance(fact.get("attribution"), dict) else {}
            user_id = attribution.get("user_id")
            if user_id is None:
                failures.append(f"owner_attribution_missing:{fact_id}")
            elif str(user_id) != case.expected_owner_id:
                failures.append(f"owner_attribution_unexpected:{fact_id}:{user_id}")
        return failures

    def _time_window_failures(
        self,
        case: WorkSummaryEvaluationCase,
        facts_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        filters = case.work_facts.get("filters") if isinstance(case.work_facts.get("filters"), dict) else {}
        starts_at = _parse_datetime(filters.get("starts_at"))
        ends_at = _parse_datetime(filters.get("ends_at"))
        if starts_at is None or ends_at is None:
            return []
        failures: list[str] = []
        for fact_id, fact in facts_by_id.items():
            occurred_at = _parse_datetime(fact.get("occurred_at"))
            if occurred_at is None:
                failures.append(f"occurred_at_missing:{fact_id}")
            elif not starts_at <= occurred_at < ends_at:
                failures.append(f"occurred_at_out_of_window:{fact_id}:{fact.get('occurred_at')}")
        return failures

    def _classification_failures(
        self,
        case: WorkSummaryEvaluationCase,
        facts_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        failures: list[str] = []
        for item in [*case.result.highlights, *case.result.customer_summaries]:
            for fact_id in item.fact_ids:
                fact = facts_by_id.get(fact_id)
                if fact is None:
                    continue
                expected = _expected_category(fact)
                if item.category != expected:
                    failures.append(f"category_unexpected:{fact_id}:{item.category}:{expected}")
        return failures

    def _truncation_failures(self, case: WorkSummaryEvaluationCase) -> list[str]:
        if not case.require_truncated_disclosure and not case.work_facts.get("truncated"):
            return []
        answer = case.result.answer or ""
        missing_context = "\n".join(case.result.missing_context or [])
        if "后续分页事实" in answer or "后续分页事实" in missing_context or "部分事实" in answer:
            return []
        return ["truncated_disclosure_missing"]

    def _answer_failures(self, case: WorkSummaryEvaluationCase) -> list[str]:
        failures: list[str] = []
        if case.min_confidence is not None and case.result.confidence < case.min_confidence:
            failures.append(f"confidence_too_low:{case.result.confidence}")
        answer_blob = "\n".join(
            [
                case.result.answer or "",
                *[item.title for item in case.result.highlights],
                *[item.summary for item in case.result.highlights],
                *[item.title for item in case.result.customer_summaries],
                *[item.summary for item in case.result.customer_summaries],
            ]
        )
        for term in case.required_answer_terms:
            if term not in answer_blob:
                failures.append(f"answer_term_absent:{term}")
        answer_lower = answer_blob.lower()
        for token in case.forbidden_answer_tokens:
            if token.lower() in answer_lower:
                failures.append(f"forbidden_token:{token}")
        return failures

    def _correction_failures(
        self,
        case: WorkSummaryEvaluationCase,
        facts_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        failures: list[str] = []
        for index, correction in enumerate(case.human_corrections):
            prefix = f"correction:{index}"
            if correction.correction_type not in WORK_SUMMARY_CORRECTION_TYPES:
                failures.append(f"{prefix}:type_invalid:{correction.correction_type}")
            if not correction.note.strip():
                failures.append(f"{prefix}:note_missing")
            if correction.target_fact_id and correction.correction_type != "missing_fact":
                if correction.target_fact_id not in facts_by_id:
                    failures.append(f"{prefix}:target_fact_unknown:{correction.target_fact_id}")
            if correction.corrected_category and correction.corrected_category not in WORK_SUMMARY_CATEGORIES:
                failures.append(f"{prefix}:category_invalid:{correction.corrected_category}")
            if correction.feedback_source != "human_review":
                failures.append(f"{prefix}:feedback_source_unexpected:{correction.feedback_source}")
        return failures

    def _metrics(self, cases: list[WorkSummaryEvaluationCase]) -> WorkSummaryAccuracyMetrics:
        recall_covered = 0
        recall_total = 0
        citation_covered = 0
        citation_total = 0
        hallucinated_refs = 0
        referenced_total = 0
        classification_errors = 0
        classification_total = 0
        correction_actionable = 0
        correction_total = 0
        owner_error_cases: list[str] = []
        owner_case_total = 0
        time_error_cases: list[str] = []
        time_case_total = 0

        for case in cases:
            facts_by_id = _facts_by_id(case.work_facts)
            referenced_fact_ids = _referenced_fact_ids(case.result)
            citations_by_id = _citations_by_id(case.result)
            recall_total += len(case.required_fact_ids)
            recall_covered += sum(1 for fact_id in case.required_fact_ids if fact_id in referenced_fact_ids)
            citation_total += sum(1 for fact_id in referenced_fact_ids if fact_id in facts_by_id)
            citation_covered += sum(1 for fact_id in referenced_fact_ids if fact_id in facts_by_id and fact_id in citations_by_id)
            referenced_total += len(referenced_fact_ids)
            hallucinated_refs += sum(1 for fact_id in referenced_fact_ids if fact_id not in facts_by_id)

            case_classification_errors = self._classification_failures(case, facts_by_id)
            classification_errors += len(case_classification_errors)
            classification_total += sum(1 for item in [*case.result.highlights, *case.result.customer_summaries] for fact_id in item.fact_ids if fact_id in facts_by_id)

            if case.expected_owner_id is not None:
                owner_case_total += 1
                if self._owner_failures(case, facts_by_id):
                    owner_error_cases.append(case.name)
            filters = case.work_facts.get("filters") if isinstance(case.work_facts.get("filters"), dict) else {}
            if filters.get("starts_at") and filters.get("ends_at"):
                time_case_total += 1
                if self._time_window_failures(case, facts_by_id):
                    time_error_cases.append(case.name)

            correction_total += len(case.human_corrections)
            correction_failures = self._correction_failures(case, facts_by_id)
            if case.human_corrections and not correction_failures:
                correction_actionable += len(case.human_corrections)

        return WorkSummaryAccuracyMetrics(
            fact_recall=WorkSummaryEvaluationMetric(recall_covered, recall_total),
            citation_completeness=WorkSummaryEvaluationMetric(citation_covered, citation_total),
            hallucination_rate=WorkSummaryEvaluationMetric(hallucinated_refs, referenced_total),
            owner_attribution_errors=WorkSummaryEvaluationMetric(
                len(owner_error_cases),
                owner_case_total,
                tuple(owner_error_cases),
            ),
            time_window_errors=WorkSummaryEvaluationMetric(
                len(time_error_cases),
                time_case_total,
                tuple(time_error_cases),
            ),
            classification_errors=WorkSummaryEvaluationMetric(classification_errors, classification_total),
            correction_actionability=WorkSummaryEvaluationMetric(correction_actionable, correction_total),
        )


def _facts_by_id(work_facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = work_facts.get("items")
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("fact_id")): item
        for item in items
        if isinstance(item, dict) and item.get("fact_id")
    }


def _referenced_fact_ids(result: WorkSummaryNarrativeResult) -> set[str]:
    return {
        fact_id
        for item in [*result.highlights, *result.customer_summaries]
        for fact_id in item.fact_ids
        if fact_id
    }


def _citations_by_id(result: WorkSummaryNarrativeResult) -> dict[str, dict[str, object]]:
    return {
        str(citation.get("fact_id")): citation
        for citation in result.citations
        if isinstance(citation, dict) and citation.get("fact_id")
    }


def _expected_category(fact: dict[str, Any]) -> str:
    fact_type = str(fact.get("fact_type") or "")
    return WORK_SUMMARY_FACT_CATEGORIES.get(fact_type, "business_progress")


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


work_summary_evaluation_service = WorkSummaryEvaluationService()
