"""Read-only transition planning for follow-up task reconciliation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.services.follow_up_task_reconciliation_evaluation_service import (
    AUTO_TRANSITION_DECISIONS,
    DEFAULT_AUTO_CONFIDENCE_THRESHOLD,
    FOLLOW_UP_TASK_RECONCILIATION_DECISIONS,
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationEvaluationCase,
    FollowUpTaskReconciliationEvaluationService,
    follow_up_task_reconciliation_evaluation_service,
)

if TYPE_CHECKING:
    from app.services.task_reconciliation_semantic_matcher import TaskReconciliationSemanticMatchResult
    from app.services.task_reconciliation_service import TaskReconciliationCandidateSet


class FollowUpTaskTransitionActionType:
    COMPLETE = "COMPLETE"
    DELAY = "DELAY"
    CANCEL = "CANCEL"
    KEEP_OPEN = "KEEP_OPEN"
    ASK_CONFIRMATION = "ASK_CONFIRMATION"
    NOOP = "NOOP"


@dataclass(frozen=True)
class FollowUpTaskTransitionAction:
    """A public-id-only transition action proposal.

    This object is intentionally read-only. It describes whether a later executor
    may mutate task state, but does not perform the mutation itself.
    """

    action: str
    task_public_id: str | None
    confidence: float
    executable: bool
    requires_confirmation: bool
    proposed_due_at: str | None = None
    reason: str | None = None
    forbid_auto_reasons: tuple[str, ...] = ()
    evidence_terms: tuple[str, ...] = ()
    source_activity_public_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "task_public_id": self.task_public_id,
            "confidence": self.confidence,
            "executable": self.executable,
            "requires_confirmation": self.requires_confirmation,
            "proposed_due_at": self.proposed_due_at,
            "reason": self.reason,
            "forbid_auto_reasons": list(self.forbid_auto_reasons),
            "evidence_terms": list(self.evidence_terms),
            "source_activity_public_id": self.source_activity_public_id,
        }


@dataclass(frozen=True)
class FollowUpTaskTransitionPlan:
    """Auditable state transition plan generated from a reconciliation decision."""

    decision: FollowUpTaskReconciliationDecision
    actions: tuple[FollowUpTaskTransitionAction, ...]
    plan_source: str
    safety_failures: tuple[str, ...] = ()
    state_mutation_requested: bool = False

    @property
    def executable_actions(self) -> tuple[FollowUpTaskTransitionAction, ...]:
        return tuple(action for action in self.actions if action.executable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": {
                "decision": self.decision.decision,
                "task_public_id": self.decision.task_public_id,
                "candidate_public_ids": list(self.decision.candidate_public_ids),
                "confidence": self.decision.confidence,
                "needs_confirmation": self.decision.needs_confirmation,
                "proposed_due_at": self.decision.proposed_due_at,
                "forbid_auto_reasons": list(self.decision.forbid_auto_reasons),
                "evidence_terms": list(self.decision.evidence_terms),
                "state_mutation_requested": self.decision.state_mutation_requested,
            },
            "actions": [action.to_dict() for action in self.actions],
            "plan_source": self.plan_source,
            "safety_failures": list(self.safety_failures),
            "state_mutation_requested": self.state_mutation_requested,
        }


class FollowUpTaskTransitionPlanService:
    """Converts semantic match suggestions into non-mutating transition plans."""

    def __init__(
        self,
        *,
        evaluation_service: FollowUpTaskReconciliationEvaluationService = (
            follow_up_task_reconciliation_evaluation_service
        ),
        auto_confidence_threshold: float = DEFAULT_AUTO_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.evaluation_service = evaluation_service
        self.auto_confidence_threshold = auto_confidence_threshold

    def plan_from_match_result(
        self,
        match_result: TaskReconciliationSemanticMatchResult,
        *,
        activity_owner_id: str | None = None,
        source_activity_public_id: str | None = None,
        plan_source: str | None = None,
    ) -> FollowUpTaskTransitionPlan:
        resolved_source_public_id = source_activity_public_id
        if resolved_source_public_id is None and match_result.referenced_source_public_ids:
            resolved_source_public_id = match_result.referenced_source_public_ids[0]
        return self.plan(
            match_result.decision,
            match_result.candidate_set,
            activity_owner_id=activity_owner_id,
            source_activity_public_id=resolved_source_public_id,
            plan_source=plan_source or match_result.source,
        )

    def plan(
        self,
        decision: FollowUpTaskReconciliationDecision,
        candidate_set: TaskReconciliationCandidateSet,
        *,
        activity_owner_id: str | None = None,
        source_activity_public_id: str | None = None,
        plan_source: str = "reconciliation_decision",
    ) -> FollowUpTaskTransitionPlan:
        safety_failures = self._safety_failures(decision, candidate_set, activity_owner_id=activity_owner_id)
        action = self._action(
            decision,
            safety_failures=safety_failures,
            source_activity_public_id=source_activity_public_id,
        )
        return FollowUpTaskTransitionPlan(
            decision=decision,
            actions=(action,),
            plan_source=plan_source,
            safety_failures=safety_failures,
            state_mutation_requested=False,
        )

    def _action(
        self,
        decision: FollowUpTaskReconciliationDecision,
        *,
        safety_failures: tuple[str, ...],
        source_activity_public_id: str | None,
    ) -> FollowUpTaskTransitionAction:
        if decision.decision == "UNRELATED":
            return self._noop_action(decision, reason="UNRELATED", source_activity_public_id=source_activity_public_id)
        if decision.decision == "KEEP_OPEN":
            return self._noop_action(decision, reason="KEEP_OPEN", source_activity_public_id=source_activity_public_id)
        if decision.decision == "ASK_CONFIRMATION" or decision.needs_confirmation:
            return FollowUpTaskTransitionAction(
                action=FollowUpTaskTransitionActionType.ASK_CONFIRMATION,
                task_public_id=decision.task_public_id,
                confidence=decision.confidence,
                executable=False,
                requires_confirmation=True,
                proposed_due_at=decision.proposed_due_at,
                reason="CONFIRMATION_REQUIRED",
                forbid_auto_reasons=tuple(dict.fromkeys((*decision.forbid_auto_reasons, *safety_failures))),
                evidence_terms=decision.evidence_terms,
                source_activity_public_id=source_activity_public_id,
            )
        if decision.decision in AUTO_TRANSITION_DECISIONS and not safety_failures:
            return FollowUpTaskTransitionAction(
                action=decision.decision,
                task_public_id=decision.task_public_id,
                confidence=decision.confidence,
                executable=True,
                requires_confirmation=False,
                proposed_due_at=decision.proposed_due_at,
                reason="AUTO_TRANSITION_ELIGIBLE",
                evidence_terms=decision.evidence_terms,
                source_activity_public_id=source_activity_public_id,
            )
        if decision.decision in AUTO_TRANSITION_DECISIONS:
            return FollowUpTaskTransitionAction(
                action=FollowUpTaskTransitionActionType.ASK_CONFIRMATION,
                task_public_id=decision.task_public_id,
                confidence=decision.confidence,
                executable=False,
                requires_confirmation=True,
                proposed_due_at=decision.proposed_due_at,
                reason="AUTO_TRANSITION_BLOCKED",
                forbid_auto_reasons=tuple(dict.fromkeys((*decision.forbid_auto_reasons, *safety_failures))),
                evidence_terms=decision.evidence_terms,
                source_activity_public_id=source_activity_public_id,
            )
        return self._noop_action(
            decision,
            reason="UNSUPPORTED_DECISION",
            source_activity_public_id=source_activity_public_id,
        )

    def _noop_action(
        self,
        decision: FollowUpTaskReconciliationDecision,
        *,
        reason: str,
        source_activity_public_id: str | None,
    ) -> FollowUpTaskTransitionAction:
        return FollowUpTaskTransitionAction(
            action=FollowUpTaskTransitionActionType.NOOP,
            task_public_id=decision.task_public_id,
            confidence=decision.confidence,
            executable=False,
            requires_confirmation=False,
            proposed_due_at=decision.proposed_due_at,
            reason=reason,
            forbid_auto_reasons=decision.forbid_auto_reasons,
            evidence_terms=decision.evidence_terms,
            source_activity_public_id=source_activity_public_id,
        )

    def _safety_failures(
        self,
        decision: FollowUpTaskReconciliationDecision,
        candidate_set: TaskReconciliationCandidateSet,
        *,
        activity_owner_id: str | None,
    ) -> tuple[str, ...]:
        failures: list[str] = []
        candidates_by_id = {candidate.public_id: candidate for candidate in candidate_set.items}
        resolved_activity_owner_id = activity_owner_id or str(candidate_set.filters.get("activity_owner_id") or "")

        if decision.decision not in FOLLOW_UP_TASK_RECONCILIATION_DECISIONS:
            failures.append(f"decision_invalid:{decision.decision}")
        if decision.state_mutation_requested:
            failures.append("state_mutation_forbidden")

        if decision.task_public_id and not decision.task_public_id.startswith("fut_"):
            failures.append(f"task_public_id_invalid:{decision.task_public_id}")
        for candidate_public_id in decision.candidate_public_ids:
            if not candidate_public_id.startswith("fut_"):
                failures.append(f"candidate_public_id_invalid:{candidate_public_id}")

        if decision.decision not in AUTO_TRANSITION_DECISIONS:
            return tuple(dict.fromkeys(failures))

        if decision.needs_confirmation:
            failures.append("confirmation_required")
        if decision.forbid_auto_reasons:
            failures.extend(decision.forbid_auto_reasons)
        if decision.confidence < self.auto_confidence_threshold:
            failures.append(f"low_confidence_auto_transition_forbidden:{decision.confidence}")
        if not decision.evidence_terms:
            failures.append("missing_evidence")
        if not decision.task_public_id:
            failures.append("auto_transition_task_missing")
            return tuple(dict.fromkeys(failures))

        selected = candidates_by_id.get(decision.task_public_id)
        if selected is None:
            failures.append(f"unknown_task_candidate:{decision.task_public_id}")
        elif not selected.auto_transition_eligible:
            failures.append(selected.confirmation_required_reason or "cross_owner_auto_transition_forbidden")

        if decision.decision == "DELAY":
            if not decision.proposed_due_at:
                failures.append("delay_due_at_missing")
            elif not self._is_valid_datetime(decision.proposed_due_at):
                failures.append("delay_due_at_invalid")

        evaluation = self.evaluation_service.evaluate_case(
            FollowUpTaskReconciliationEvaluationCase(
                name="transition_plan_guardrail",
                activity_owner_id=resolved_activity_owner_id,
                task_owner_by_public_id={candidate.public_id: candidate.owner_id for candidate in candidate_set.items},
                result=decision,
                allowed_decisions=set(FOLLOW_UP_TASK_RECONCILIATION_DECISIONS),
                auto_confidence_threshold=self.auto_confidence_threshold,
            )
        )
        failures.extend(evaluation.failures)
        return tuple(dict.fromkeys(failures))

    def _is_valid_datetime(self, value: str) -> bool:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True


follow_up_task_transition_plan_service = FollowUpTaskTransitionPlanService()
