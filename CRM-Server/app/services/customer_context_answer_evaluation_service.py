"""Contract evaluation helpers for customer context answers."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.agent.schemas import CustomerContextAnswerResult

DEFAULT_FORBIDDEN_TOKENS = (
    "source_type",
    "source_object_id",
    "business_object_id",
    "business_object_type",
    "tool",
    "payload",
    "procurement_method_id",
    "customer_id",
    "opportunity_id",
    "contract_id",
    "payment_plan_id",
    "payment_record_id",
    "evidence_id",
    "document_key",
)


@dataclass(frozen=True)
class CustomerContextAnswerEvaluationCase:
    """A stable regression case for CRM answer grounding behavior."""

    name: str
    result: CustomerContextAnswerResult
    retrieval_status: str | None = None
    allowed_answer_modes: set[str] = field(default_factory=set)
    require_citations: bool = False
    forbid_citations: bool = False
    min_confidence: float | None = None
    required_answer_terms: tuple[str, ...] = ()
    required_missing_context_terms: tuple[str, ...] = ()
    forbidden_answer_tokens: tuple[str, ...] = DEFAULT_FORBIDDEN_TOKENS


@dataclass(frozen=True)
class CustomerContextAnswerEvaluationResult:
    case_name: str
    passed: bool
    failures: list[str]


@dataclass(frozen=True)
class CustomerContextAnswerEvaluationSummary:
    total: int
    passed: int
    failed: int
    results: list[CustomerContextAnswerEvaluationResult]

    @property
    def ok(self) -> bool:
        return self.failed == 0


@dataclass(frozen=True)
class CustomerContextAnswerEvaluationService:
    """Evaluates answer contract quality without calling an LLM."""

    def evaluate_case(
        self,
        case: CustomerContextAnswerEvaluationCase,
    ) -> CustomerContextAnswerEvaluationResult:
        failures: list[str] = []
        result = case.result

        if case.allowed_answer_modes and result.answer_mode not in case.allowed_answer_modes:
            failures.append(
                f"answer_mode_unexpected:{result.answer_mode}",
            )

        citations = result.citations or []
        if case.require_citations and not citations:
            failures.append("citations_missing")
        if case.forbid_citations and citations:
            failures.append("citations_forbidden")
        if case.retrieval_status and case.retrieval_status != "ok" and citations:
            failures.append("citations_present_without_ok_retrieval")
        if case.min_confidence is not None and result.confidence < case.min_confidence:
            failures.append(f"confidence_too_low:{result.confidence}")

        answer_lower = (result.answer or "").lower()
        for term in case.required_answer_terms:
            if term not in result.answer:
                failures.append(f"answer_term_absent:{term}")
        for token in case.forbidden_answer_tokens:
            if token.lower() in answer_lower:
                failures.append(f"forbidden_token:{token}")

        missing_context_text = "\n".join(result.missing_context or [])
        for term in case.required_missing_context_terms:
            if term not in missing_context_text:
                failures.append(f"missing_context_term_absent:{term}")

        return CustomerContextAnswerEvaluationResult(
            case_name=case.name,
            passed=not failures,
            failures=failures,
        )

    def evaluate_many(
        self,
        cases: list[CustomerContextAnswerEvaluationCase],
    ) -> CustomerContextAnswerEvaluationSummary:
        results = [self.evaluate_case(case) for case in cases]
        passed = sum(1 for result in results if result.passed)
        return CustomerContextAnswerEvaluationSummary(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=results,
        )


customer_context_answer_evaluation_service = CustomerContextAnswerEvaluationService()
