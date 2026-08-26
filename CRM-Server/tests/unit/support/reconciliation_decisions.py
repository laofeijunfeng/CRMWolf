"""Test factories for the canonical follow-up reconciliation batch contract."""

from app.services.follow_up_task_reconciliation_evaluation_service import (
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationTaskDecision,
)


def single_task_reconciliation_decision(
    *,
    decision: str,
    task_public_id: str,
    confidence: float,
    needs_confirmation: bool = False,
    proposed_due_at: str | None = None,
    forbid_auto_reasons: tuple[str, ...] = (),
    evidence_terms: tuple[str, ...] = (),
    state_mutation_requested: bool = False,
) -> FollowUpTaskReconciliationDecision:
    """Build the one-item form of the canonical batch result."""

    return FollowUpTaskReconciliationDecision(
        candidate_public_ids=(task_public_id,),
        task_decisions=(
            FollowUpTaskReconciliationTaskDecision(
                decision=decision,
                task_public_id=task_public_id,
                confidence=confidence,
                needs_confirmation=needs_confirmation,
                proposed_due_at=proposed_due_at,
                forbid_auto_reasons=forbid_auto_reasons,
                evidence_terms=evidence_terms,
                state_mutation_requested=state_mutation_requested,
            ),
        ),
    )


def empty_reconciliation_decision(
    *,
    reason: str,
    confidence: float = 1.0,
    evidence_terms: tuple[str, ...] = (),
) -> FollowUpTaskReconciliationDecision:
    """Build the explicit no-candidate outcome."""

    return FollowUpTaskReconciliationDecision(
        candidate_public_ids=(),
        task_decisions=(),
        empty_reason=reason,
        empty_confidence=confidence,
        empty_evidence_terms=evidence_terms,
    )
