import pytest

from app.services.follow_up_task_reconciliation_evaluation_service import (
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationEvaluationCase,
    FollowUpTaskReconciliationEvaluationService,
)


def test_reconciliation_evaluation_accepts_same_owner_completion_without_mutation():
    service = FollowUpTaskReconciliationEvaluationService()

    evaluation = service.evaluate_case(
        FollowUpTaskReconciliationEvaluationCase(
            name="same_owner_completed_budget_check",
            activity_owner_id="user-sales-1",
            task_owner_by_public_id={"fut_budget_check": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision="COMPLETE",
                task_public_id="fut_budget_check",
                candidate_public_ids=("fut_budget_check",),
                confidence=0.93,
                evidence_terms=("预算已经通过",),
            ),
            expected_decision="COMPLETE",
            expected_task_public_id="fut_budget_check",
            required_candidate_public_ids=("fut_budget_check",),
            min_confidence=0.9,
            forbid_confirmation=True,
            required_evidence_terms=("预算",),
        ),
    )

    assert evaluation.passed is True
    assert evaluation.failures == []


@pytest.mark.parametrize(
    ("decision", "proposed_due_at"),
    [
        ("COMPLETE", None),
        ("DELAY", "2026-08-14T00:00:00"),
        ("CANCEL", None),
    ],
)
def test_reconciliation_evaluation_rejects_cross_owner_auto_transitions(decision, proposed_due_at):
    service = FollowUpTaskReconciliationEvaluationService()

    evaluation = service.evaluate_case(
        FollowUpTaskReconciliationEvaluationCase(
            name=f"cross_owner_bad_auto_{decision.lower()}",
            activity_owner_id="user-presales-1",
            task_owner_by_public_id={"fut_sales_budget": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision=decision,
                task_public_id="fut_sales_budget",
                candidate_public_ids=("fut_sales_budget",),
                confidence=0.96,
                proposed_due_at=proposed_due_at,
                evidence_terms=("预算已经通过",),
                state_mutation_requested=True,
            ),
            expected_decision="ASK_CONFIRMATION",
            expected_task_public_id="fut_sales_budget",
            require_confirmation=True,
        ),
    )

    assert evaluation.passed is False
    assert f"decision_unexpected:{decision}" in evaluation.failures
    assert "confirmation_required" in evaluation.failures
    assert "state_mutation_forbidden" in evaluation.failures
    assert "cross_owner_auto_transition_forbidden:fut_sales_budget" in evaluation.failures


def test_reconciliation_evaluation_rejects_low_confidence_auto_delay():
    service = FollowUpTaskReconciliationEvaluationService()

    evaluation = service.evaluate_case(
        FollowUpTaskReconciliationEvaluationCase(
            name="low_confidence_bad_delay",
            activity_owner_id="user-sales-1",
            task_owner_by_public_id={"fut_budget_check": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision="DELAY",
                task_public_id="fut_budget_check",
                candidate_public_ids=("fut_budget_check",),
                confidence=0.64,
                proposed_due_at="2026-08-14T00:00:00",
                evidence_terms=("下周五",),
            ),
            expected_decision="ASK_CONFIRMATION",
            expected_task_public_id="fut_budget_check",
            require_confirmation=True,
        ),
    )

    assert evaluation.passed is False
    assert "decision_unexpected:DELAY" in evaluation.failures
    assert "confirmation_required" in evaluation.failures
    assert "low_confidence_auto_transition_forbidden:0.64" in evaluation.failures


def test_reconciliation_evaluation_summarizes_failed_contract_checks():
    service = FollowUpTaskReconciliationEvaluationService()

    summary = service.evaluate_many([
        FollowUpTaskReconciliationEvaluationCase(
            name="valid_unrelated",
            activity_owner_id="user-sales-1",
            task_owner_by_public_id={"fut_budget_check": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision="UNRELATED",
                candidate_public_ids=("fut_budget_check",),
                confidence=0.82,
                evidence_terms=("演示",),
            ),
            expected_decision="UNRELATED",
        ),
        FollowUpTaskReconciliationEvaluationCase(
            name="invalid_internal_id",
            activity_owner_id="user-sales-1",
            task_owner_by_public_id={"fut_budget_check": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision="COMPLETE",
                task_public_id="123",
                candidate_public_ids=("123",),
                confidence=0.91,
                evidence_terms=("预算",),
            ),
            expected_decision="COMPLETE",
        ),
    ])

    assert summary.ok is False
    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.results[1].failures == [
        "task_public_id_invalid:123",
        "candidate_public_id_invalid:123",
        "unknown_task_candidate:123",
    ]


def test_reconciliation_evaluation_computes_safety_metrics():
    service = FollowUpTaskReconciliationEvaluationService()

    summary = service.evaluate_many([
        FollowUpTaskReconciliationEvaluationCase(
            name="false_close",
            activity_owner_id="user-sales-1",
            task_owner_by_public_id={"fut_budget_check": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision="COMPLETE",
                task_public_id="fut_budget_check",
                candidate_public_ids=("fut_budget_check",),
                confidence=0.96,
                evidence_terms=("预算",),
            ),
            expected_decision="ASK_CONFIRMATION",
            require_confirmation=True,
        ),
        FollowUpTaskReconciliationEvaluationCase(
            name="false_delay",
            activity_owner_id="user-sales-1",
            task_owner_by_public_id={"fut_budget_check": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision="DELAY",
                task_public_id="fut_budget_check",
                candidate_public_ids=("fut_budget_check",),
                confidence=0.9,
                proposed_due_at="2026-08-14T00:00:00",
                evidence_terms=("下周五",),
            ),
            expected_decision="KEEP_OPEN",
        ),
        FollowUpTaskReconciliationEvaluationCase(
            name="over_confirmation",
            activity_owner_id="user-sales-1",
            task_owner_by_public_id={"fut_demo": "user-sales-1"},
            result=FollowUpTaskReconciliationDecision(
                decision="ASK_CONFIRMATION",
                task_public_id="fut_demo",
                candidate_public_ids=("fut_demo",),
                confidence=0.82,
                needs_confirmation=True,
                evidence_terms=("演示",),
            ),
            expected_decision="UNRELATED",
            forbid_confirmation=True,
        ),
    ])

    metrics = summary.metrics.to_dict()

    assert metrics["false_close"]["count"] == 1
    assert metrics["false_close"]["rate"] == 0.3333
    assert metrics["false_close"]["case_names"] == ["false_close"]
    assert metrics["false_delay"]["count"] == 1
    assert metrics["missed_confirmation"]["count"] == 1
    assert metrics["over_confirmation"]["count"] == 1
    assert summary.to_dict()["metrics"] == metrics
