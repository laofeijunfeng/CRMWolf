"""Deterministic evaluation helpers for follow-up task reconciliation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

FOLLOW_UP_TASK_RECONCILIATION_DECISIONS = {
    "COMPLETE",
    "DELAY",
    "CANCEL",
    "KEEP_OPEN",
    "UNRELATED",
    "ASK_CONFIRMATION",
}
AUTO_TRANSITION_DECISIONS = {"COMPLETE", "DELAY", "CANCEL"}
DEFAULT_AUTO_CONFIDENCE_THRESHOLD = 0.85


@dataclass(frozen=True)
class FollowUpTaskReconciliationDecision:
    """A candidate reconciliation result produced by rules or a future LLM matcher."""

    decision: str
    confidence: float
    task_public_id: str | None = None
    candidate_public_ids: tuple[str, ...] = ()
    needs_confirmation: bool = False
    proposed_due_at: str | None = None
    forbid_auto_reasons: tuple[str, ...] = ()
    evidence_terms: tuple[str, ...] = ()
    state_mutation_requested: bool = False


@dataclass(frozen=True)
class FollowUpTaskReconciliationEvaluationCase:
    """A stable regression case for auto-close/delay/cancel safety."""

    name: str
    activity_owner_id: str
    task_owner_by_public_id: dict[str, str]
    result: FollowUpTaskReconciliationDecision
    expected_decision: str | None = None
    allowed_decisions: set[str] = field(default_factory=set)
    expected_task_public_id: str | None = None
    required_candidate_public_ids: tuple[str, ...] = ()
    forbidden_candidate_public_ids: tuple[str, ...] = ()
    min_confidence: float | None = None
    max_confidence: float | None = None
    require_confirmation: bool = False
    forbid_confirmation: bool = False
    required_forbid_auto_reasons: tuple[str, ...] = ()
    required_evidence_terms: tuple[str, ...] = ()
    forbid_state_mutation: bool = True
    require_public_ids: bool = True
    auto_confidence_threshold: float = DEFAULT_AUTO_CONFIDENCE_THRESHOLD
    allow_cross_owner_auto_transition: bool = False


@dataclass(frozen=True)
class FollowUpTaskReconciliationEvaluationResult:
    case_name: str
    passed: bool
    failures: list[str]


@dataclass(frozen=True)
class FollowUpTaskReconciliationEvaluationMetric:
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
class FollowUpTaskReconciliationSafetyMetrics:
    false_close: FollowUpTaskReconciliationEvaluationMetric
    false_delay: FollowUpTaskReconciliationEvaluationMetric
    missed_confirmation: FollowUpTaskReconciliationEvaluationMetric
    over_confirmation: FollowUpTaskReconciliationEvaluationMetric

    def to_dict(self) -> dict[str, object]:
        return {
            "false_close": self.false_close.to_dict(),
            "false_delay": self.false_delay.to_dict(),
            "missed_confirmation": self.missed_confirmation.to_dict(),
            "over_confirmation": self.over_confirmation.to_dict(),
        }


def _empty_safety_metrics() -> FollowUpTaskReconciliationSafetyMetrics:
    empty_metric = FollowUpTaskReconciliationEvaluationMetric(count=0, denominator=0)
    return FollowUpTaskReconciliationSafetyMetrics(
        false_close=empty_metric,
        false_delay=empty_metric,
        missed_confirmation=empty_metric,
        over_confirmation=empty_metric,
    )


@dataclass(frozen=True)
class FollowUpTaskReconciliationEvaluationSummary:
    total: int
    passed: int
    failed: int
    results: list[FollowUpTaskReconciliationEvaluationResult]
    metrics: FollowUpTaskReconciliationSafetyMetrics = field(default_factory=_empty_safety_metrics)

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
class FollowUpTaskReconciliationEvaluationService:
    """Evaluates reconciliation safety contracts without calling an LLM or mutating tasks."""

    def evaluate_case(
        self,
        case: FollowUpTaskReconciliationEvaluationCase,
    ) -> FollowUpTaskReconciliationEvaluationResult:
        failures: list[str] = []
        result = case.result

        if result.decision not in FOLLOW_UP_TASK_RECONCILIATION_DECISIONS:
            failures.append(f"decision_invalid:{result.decision}")
        if case.expected_decision and result.decision != case.expected_decision:
            failures.append(f"decision_unexpected:{result.decision}")
        if case.allowed_decisions and result.decision not in case.allowed_decisions:
            failures.append(f"decision_not_allowed:{result.decision}")
        if case.expected_task_public_id is not None and result.task_public_id != case.expected_task_public_id:
            failures.append(f"task_public_id_unexpected:{result.task_public_id}")

        if case.require_public_ids:
            failures.extend(self._public_id_failures(result))

        for candidate_public_id in case.required_candidate_public_ids:
            if candidate_public_id not in result.candidate_public_ids:
                failures.append(f"candidate_missing:{candidate_public_id}")
        for candidate_public_id in case.forbidden_candidate_public_ids:
            if candidate_public_id in result.candidate_public_ids:
                failures.append(f"candidate_forbidden:{candidate_public_id}")

        if case.min_confidence is not None and result.confidence < case.min_confidence:
            failures.append(f"confidence_too_low:{result.confidence}")
        if case.max_confidence is not None and result.confidence > case.max_confidence:
            failures.append(f"confidence_too_high:{result.confidence}")

        if case.require_confirmation and not result.needs_confirmation:
            failures.append("confirmation_required")
        if case.forbid_confirmation and result.needs_confirmation:
            failures.append("confirmation_forbidden")
        if result.decision == "ASK_CONFIRMATION" and not result.needs_confirmation:
            failures.append("confirmation_flag_missing")

        if case.forbid_state_mutation and result.state_mutation_requested:
            failures.append("state_mutation_forbidden")

        for reason in case.required_forbid_auto_reasons:
            if reason not in result.forbid_auto_reasons:
                failures.append(f"forbid_auto_reason_absent:{reason}")
        evidence_text = "\n".join(result.evidence_terms)
        for term in case.required_evidence_terms:
            if term not in evidence_text:
                failures.append(f"evidence_term_absent:{term}")

        failures.extend(self._transition_safety_failures(case))

        return FollowUpTaskReconciliationEvaluationResult(
            case_name=case.name,
            passed=not failures,
            failures=failures,
        )

    def evaluate_many(
        self,
        cases: list[FollowUpTaskReconciliationEvaluationCase],
    ) -> FollowUpTaskReconciliationEvaluationSummary:
        results = [self.evaluate_case(case) for case in cases]
        passed = sum(1 for result in results if result.passed)
        return FollowUpTaskReconciliationEvaluationSummary(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=results,
            metrics=self._safety_metrics(cases),
        )

    def _safety_metrics(
        self,
        cases: list[FollowUpTaskReconciliationEvaluationCase],
    ) -> FollowUpTaskReconciliationSafetyMetrics:
        total = len(cases)
        false_close_cases: list[str] = []
        false_delay_cases: list[str] = []
        missed_confirmation_cases: list[str] = []
        over_confirmation_cases: list[str] = []

        for case in cases:
            decision = case.result.decision
            if decision == "COMPLETE" and not self._decision_is_expected(case, "COMPLETE"):
                false_close_cases.append(case.name)
            if decision == "DELAY" and not self._decision_is_expected(case, "DELAY"):
                false_delay_cases.append(case.name)
            if case.require_confirmation and (decision != "ASK_CONFIRMATION" or not case.result.needs_confirmation):
                missed_confirmation_cases.append(case.name)
            if case.forbid_confirmation and (decision == "ASK_CONFIRMATION" or case.result.needs_confirmation):
                over_confirmation_cases.append(case.name)

        return FollowUpTaskReconciliationSafetyMetrics(
            false_close=self._metric(false_close_cases, total),
            false_delay=self._metric(false_delay_cases, total),
            missed_confirmation=self._metric(missed_confirmation_cases, total),
            over_confirmation=self._metric(over_confirmation_cases, total),
        )

    def _metric(
        self,
        case_names: list[str],
        denominator: int,
    ) -> FollowUpTaskReconciliationEvaluationMetric:
        return FollowUpTaskReconciliationEvaluationMetric(
            count=len(case_names),
            denominator=denominator,
            case_names=tuple(case_names),
        )

    def _decision_is_expected(
        self,
        case: FollowUpTaskReconciliationEvaluationCase,
        decision: str,
    ) -> bool:
        if case.allowed_decisions:
            return decision in case.allowed_decisions
        if case.expected_decision is not None:
            return decision == case.expected_decision
        return True

    def _transition_safety_failures(self, case: FollowUpTaskReconciliationEvaluationCase) -> list[str]:
        result = case.result
        if result.decision == "UNRELATED" and result.task_public_id is not None:
            return [f"unrelated_task_present:{result.task_public_id}"]
        if result.decision == "DELAY" and not result.proposed_due_at:
            return ["delay_due_at_missing"]
        if result.decision not in AUTO_TRANSITION_DECISIONS or result.needs_confirmation:
            return []

        failures: list[str] = []
        if result.confidence < case.auto_confidence_threshold:
            failures.append(f"low_confidence_auto_transition_forbidden:{result.confidence}")
        if result.task_public_id is None:
            failures.append("auto_transition_task_missing")
            return failures

        task_owner_id = case.task_owner_by_public_id.get(result.task_public_id)
        if task_owner_id is None:
            failures.append(f"unknown_task_candidate:{result.task_public_id}")
        elif task_owner_id != case.activity_owner_id and not case.allow_cross_owner_auto_transition:
            failures.append(f"cross_owner_auto_transition_forbidden:{result.task_public_id}")
        return failures

    def _public_id_failures(self, result: FollowUpTaskReconciliationDecision) -> list[str]:
        failures: list[str] = []
        if result.task_public_id is not None and not result.task_public_id.startswith("fut_"):
            failures.append(f"task_public_id_invalid:{result.task_public_id}")
        for candidate_public_id in result.candidate_public_ids:
            if not candidate_public_id.startswith("fut_"):
                failures.append(f"candidate_public_id_invalid:{candidate_public_id}")
        return failures


follow_up_task_reconciliation_evaluation_service = FollowUpTaskReconciliationEvaluationService()
