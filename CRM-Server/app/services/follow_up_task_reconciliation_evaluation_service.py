"""Deterministic evaluation helpers for follow-up task reconciliation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

FOLLOW_UP_TASK_RECONCILIATION_DECISIONS = {
    "COMPLETE",
    "POSTPONE",
    "CANCEL",
    "KEEP_OPEN",
    "UNRELATED",
    "ASK_CONFIRMATION",
}
AUTO_TRANSITION_DECISIONS = {"COMPLETE", "POSTPONE", "CANCEL"}
DEFAULT_AUTO_CONFIDENCE_THRESHOLD = 0.85


@dataclass(frozen=True)
class FollowUpTaskReconciliationTaskDecision:
    """A decision for exactly one open follow-up task."""

    decision: str
    confidence: float
    task_public_id: str
    needs_confirmation: bool = False
    proposed_due_at: str | None = None
    forbid_auto_reasons: tuple[str, ...] = ()
    evidence_terms: tuple[str, ...] = ()
    state_mutation_requested: bool = False


@dataclass(frozen=True)
class FollowUpTaskReconciliationDecision:
    """Batch reconciliation result with exactly one decision per candidate task.

    Candidate/task alignment is the single source of truth. No scalar projection
    is exposed because it would create a second representation that can drift
    from ``task_decisions``.
    """

    candidate_public_ids: tuple[str, ...]
    task_decisions: tuple[FollowUpTaskReconciliationTaskDecision, ...]
    empty_reason: str | None = None
    empty_confidence: float = 1.0
    empty_evidence_terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.candidate_public_ids) != len(set(self.candidate_public_ids)):
            raise ValueError("candidate_public_ids must be unique")
        task_public_ids = tuple(item.task_public_id for item in self.task_decisions)
        if len(task_public_ids) != len(set(task_public_ids)):
            raise ValueError("task_decisions must contain unique task_public_id values")
        if task_public_ids != self.candidate_public_ids:
            raise ValueError("task_decisions must align one-to-one with candidate_public_ids")
        if self.task_decisions and self.empty_reason is not None:
            raise ValueError("empty_reason is only valid when there are no candidate tasks")
        if not 0 <= self.empty_confidence <= 1:
            raise ValueError("empty_confidence must be between 0 and 1")

    def task_decisions_to_dict(self) -> list[dict[str, object]]:
        return [
            {
                "decision": item.decision,
                "task_public_id": item.task_public_id,
                "confidence": item.confidence,
                "needs_confirmation": item.needs_confirmation,
                "proposed_due_at": item.proposed_due_at,
                "forbid_auto_reasons": list(item.forbid_auto_reasons),
                "evidence_terms": list(item.evidence_terms),
                "state_mutation_requested": item.state_mutation_requested,
            }
            for item in self.task_decisions
        ]


@dataclass(frozen=True)
class FollowUpTaskReconciliationEvaluationCase:
    """A stable regression case for auto-close/postpone/cancel safety."""

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
    false_postpone: FollowUpTaskReconciliationEvaluationMetric
    missed_confirmation: FollowUpTaskReconciliationEvaluationMetric
    over_confirmation: FollowUpTaskReconciliationEvaluationMetric

    def to_dict(self) -> dict[str, object]:
        return {
            "false_close": self.false_close.to_dict(),
            "false_postpone": self.false_postpone.to_dict(),
            "missed_confirmation": self.missed_confirmation.to_dict(),
            "over_confirmation": self.over_confirmation.to_dict(),
        }


def _empty_safety_metrics() -> FollowUpTaskReconciliationSafetyMetrics:
    empty_metric = FollowUpTaskReconciliationEvaluationMetric(count=0, denominator=0)
    return FollowUpTaskReconciliationSafetyMetrics(
        false_close=empty_metric,
        false_postpone=empty_metric,
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
        single_task_decision = result.task_decisions[0] if len(result.task_decisions) == 1 else None
        confidence = (
            min(item.confidence for item in result.task_decisions)
            if result.task_decisions
            else result.empty_confidence
        )
        needs_confirmation = any(item.needs_confirmation for item in result.task_decisions)
        state_mutation_requested = any(item.state_mutation_requested for item in result.task_decisions)
        forbid_auto_reasons = tuple(
            dict.fromkeys(reason for item in result.task_decisions for reason in item.forbid_auto_reasons)
        )
        evidence_terms = tuple(dict.fromkeys(term for item in result.task_decisions for term in item.evidence_terms))

        for task_decision in result.task_decisions:
            if task_decision.decision not in FOLLOW_UP_TASK_RECONCILIATION_DECISIONS:
                failures.append(f"decision_invalid:{task_decision.decision}")
            if task_decision.decision == "ASK_CONFIRMATION" and not task_decision.needs_confirmation:
                failures.append("confirmation_flag_missing")
        if case.expected_decision and (
            single_task_decision is None or single_task_decision.decision != case.expected_decision
        ):
            actual_decision = single_task_decision.decision if single_task_decision is not None else None
            failures.append(f"decision_unexpected:{actual_decision}")
        if case.allowed_decisions:
            for task_decision in result.task_decisions:
                if task_decision.decision not in case.allowed_decisions:
                    failures.append(f"decision_not_allowed:{task_decision.decision}")
        if case.expected_task_public_id is not None and (
            single_task_decision is None or single_task_decision.task_public_id != case.expected_task_public_id
        ):
            actual_task_public_id = single_task_decision.task_public_id if single_task_decision is not None else None
            failures.append(f"task_public_id_unexpected:{actual_task_public_id}")

        if case.require_public_ids:
            failures.extend(self._public_id_failures(result))

        for candidate_public_id in case.required_candidate_public_ids:
            if candidate_public_id not in result.candidate_public_ids:
                failures.append(f"candidate_missing:{candidate_public_id}")
        for candidate_public_id in case.forbidden_candidate_public_ids:
            if candidate_public_id in result.candidate_public_ids:
                failures.append(f"candidate_forbidden:{candidate_public_id}")

        if case.min_confidence is not None and confidence < case.min_confidence:
            failures.append(f"confidence_too_low:{confidence}")
        if case.max_confidence is not None and confidence > case.max_confidence:
            failures.append(f"confidence_too_high:{confidence}")

        if case.require_confirmation and not needs_confirmation:
            failures.append("confirmation_required")
        if case.forbid_confirmation and needs_confirmation:
            failures.append("confirmation_forbidden")
        if case.forbid_state_mutation and state_mutation_requested:
            failures.append("state_mutation_forbidden")

        for reason in case.required_forbid_auto_reasons:
            if reason not in forbid_auto_reasons:
                failures.append(f"forbid_auto_reason_absent:{reason}")
        evidence_text = "\n".join(evidence_terms)
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
        false_postpone_cases: list[str] = []
        missed_confirmation_cases: list[str] = []
        over_confirmation_cases: list[str] = []

        for case in cases:
            decisions = case.result.task_decisions
            if any(item.decision == "COMPLETE" for item in decisions) and not self._decision_is_expected(
                case, "COMPLETE"
            ):
                false_close_cases.append(case.name)
            if any(item.decision == "POSTPONE" for item in decisions) and not self._decision_is_expected(case, "POSTPONE"):
                false_postpone_cases.append(case.name)
            needs_confirmation = any(item.needs_confirmation for item in decisions)
            asks_confirmation = any(item.decision == "ASK_CONFIRMATION" for item in decisions)
            if case.require_confirmation and (not asks_confirmation or not needs_confirmation):
                missed_confirmation_cases.append(case.name)
            if case.forbid_confirmation and (asks_confirmation or needs_confirmation):
                over_confirmation_cases.append(case.name)

        return FollowUpTaskReconciliationSafetyMetrics(
            false_close=self._metric(false_close_cases, total),
            false_postpone=self._metric(false_postpone_cases, total),
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
        failures: list[str] = []
        for decision in case.result.task_decisions:
            if decision.decision == "UNRELATED" and decision.task_public_id not in case.result.candidate_public_ids:
                failures.append(f"unrelated_task_not_candidate:{decision.task_public_id}")
                continue
            if decision.decision == "POSTPONE" and not decision.proposed_due_at:
                failures.append("postpone_due_at_missing")
            if decision.decision not in AUTO_TRANSITION_DECISIONS or decision.needs_confirmation:
                continue
            if decision.confidence < case.auto_confidence_threshold:
                failures.append(f"low_confidence_auto_transition_forbidden:{decision.confidence}")

            task_owner_id = case.task_owner_by_public_id.get(decision.task_public_id)
            if task_owner_id is None:
                failures.append(f"unknown_task_candidate:{decision.task_public_id}")
            elif task_owner_id != case.activity_owner_id and not case.allow_cross_owner_auto_transition:
                failures.append(f"cross_owner_auto_transition_forbidden:{decision.task_public_id}")
        return failures

    def _public_id_failures(self, result: FollowUpTaskReconciliationDecision) -> list[str]:
        failures: list[str] = []
        for decision in result.task_decisions:
            if not decision.task_public_id.startswith("fut_"):
                failures.append(f"task_public_id_invalid:{decision.task_public_id}")
        for candidate_public_id in result.candidate_public_ids:
            if not candidate_public_id.startswith("fut_"):
                failures.append(f"candidate_public_id_invalid:{candidate_public_id}")
        return failures


follow_up_task_reconciliation_evaluation_service = FollowUpTaskReconciliationEvaluationService()
