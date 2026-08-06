import pytest

from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionActionType,
    FollowUpTaskTransitionPlanService,
)
from app.services.task_reconciliation_semantic_matcher import TaskReconciliationSemanticMatchResult
from app.services.task_reconciliation_service import TaskReconciliationCandidate, TaskReconciliationCandidateSet


def _candidate(
    public_id: str = "fut_11111111111111111111111111111111",
    *,
    owner_id: str = "2",
    auto_transition_eligible: bool = True,
    confirmation_required_reason: str | None = None,
) -> TaskReconciliationCandidate:
    return TaskReconciliationCandidate(
        public_id=public_id,
        owner_id=owner_id,
        title="确认客户预算是否通过",
        description="客户说本周确认预算。",
        due_at="2026-08-05T10:00:00",
        due_at_text="本周三",
        due_at_granularity="DATETIME",
        due_at_timezone="Asia/Shanghai",
        source_type="CUSTOMER_ACTIVITY",
        source_public_id="act_11111111111111111111111111111111",
        confidence=0.91,
        candidate_reasons=("same_customer", "open_task", "due_window", "same_owner"),
        auto_transition_eligible=auto_transition_eligible,
        confirmation_required_reason=confirmation_required_reason,
    )


def _candidate_set(*items: TaskReconciliationCandidate, activity_owner_id: str = "2") -> TaskReconciliationCandidateSet:
    return TaskReconciliationCandidateSet(
        items=list(items),
        total=len(items),
        filters={"activity_owner_id": activity_owner_id},
        usage_policy={
            "state_source": "mysql.crm_follow_up_tasks",
            "mutation": "forbidden",
            "cross_owner": "confirmation_only",
        },
    )


def test_transition_plan_marks_same_owner_high_confidence_completion_executable():
    task = _candidate()
    service = FollowUpTaskTransitionPlanService()

    plan = service.plan(
        FollowUpTaskReconciliationDecision(
            decision="COMPLETE",
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.94,
            evidence_terms=("预算已经通过", "确认客户预算"),
        ),
        _candidate_set(task),
        source_activity_public_id="act_22222222222222222222222222222222",
    )

    assert plan.state_mutation_requested is False
    assert plan.safety_failures == ()
    assert len(plan.executable_actions) == 1
    action = plan.actions[0]
    assert action.action == FollowUpTaskTransitionActionType.COMPLETE
    assert action.task_public_id == task.public_id
    assert action.executable is True
    assert action.requires_confirmation is False
    assert action.reason == "AUTO_TRANSITION_ELIGIBLE"


def test_transition_plan_blocks_delay_without_valid_due_at():
    task = _candidate()
    service = FollowUpTaskTransitionPlanService()

    plan = service.plan(
        FollowUpTaskReconciliationDecision(
            decision="DELAY",
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.93,
            proposed_due_at="下周五",
            evidence_terms=("下周五", "确认客户预算"),
        ),
        _candidate_set(task),
    )

    assert plan.executable_actions == ()
    assert "delay_due_at_invalid" in plan.safety_failures
    assert plan.actions[0].action == FollowUpTaskTransitionActionType.ASK_CONFIRMATION
    assert plan.actions[0].requires_confirmation is True
    assert plan.actions[0].executable is False


@pytest.mark.parametrize(
    ("decision", "proposed_due_at"),
    [
        ("COMPLETE", None),
        ("DELAY", "2026-08-14T10:00:00"),
        ("CANCEL", None),
    ],
)
def test_transition_plan_blocks_cross_owner_and_low_confidence_auto_transition(decision, proposed_due_at):
    task = _candidate(
        owner_id="3",
        auto_transition_eligible=False,
        confirmation_required_reason="CROSS_OWNER",
    )
    service = FollowUpTaskTransitionPlanService()

    plan = service.plan(
        FollowUpTaskReconciliationDecision(
            decision=decision,
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.62,
            proposed_due_at=proposed_due_at,
            evidence_terms=("预算已经通过",),
        ),
        _candidate_set(task, activity_owner_id="2"),
    )

    assert plan.executable_actions == ()
    assert "CROSS_OWNER" in plan.safety_failures
    assert "low_confidence_auto_transition_forbidden:0.62" in plan.safety_failures
    assert f"cross_owner_auto_transition_forbidden:{task.public_id}" in plan.safety_failures
    assert plan.actions[0].action == FollowUpTaskTransitionActionType.ASK_CONFIRMATION


def test_transition_plan_blocks_forbid_reasons_and_unknown_candidates():
    task = _candidate()
    service = FollowUpTaskTransitionPlanService()

    plan = service.plan(
        FollowUpTaskReconciliationDecision(
            decision="CANCEL",
            task_public_id="fut_99999999999999999999999999999999",
            candidate_public_ids=(task.public_id,),
            confidence=0.91,
            forbid_auto_reasons=("HIGH_VALUE_CUSTOMER_REVIEW_REQUIRED",),
            evidence_terms=("不用管了",),
        ),
        _candidate_set(task),
    )

    assert plan.executable_actions == ()
    assert "HIGH_VALUE_CUSTOMER_REVIEW_REQUIRED" in plan.safety_failures
    assert "unknown_task_candidate:fut_99999999999999999999999999999999" in plan.safety_failures
    assert plan.actions[0].action == FollowUpTaskTransitionActionType.ASK_CONFIRMATION


def test_transition_plan_maps_keep_open_and_unrelated_to_noop():
    task = _candidate()
    service = FollowUpTaskTransitionPlanService()

    keep_open_plan = service.plan(
        FollowUpTaskReconciliationDecision(
            decision="KEEP_OPEN",
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.88,
            evidence_terms=("还没有进展",),
        ),
        _candidate_set(task),
    )
    unrelated_plan = service.plan(
        FollowUpTaskReconciliationDecision(
            decision="UNRELATED",
            candidate_public_ids=(task.public_id,),
            confidence=0.9,
            evidence_terms=("演示",),
        ),
        _candidate_set(task),
    )

    assert keep_open_plan.actions[0].action == FollowUpTaskTransitionActionType.NOOP
    assert keep_open_plan.actions[0].reason == "KEEP_OPEN"
    assert unrelated_plan.actions[0].action == FollowUpTaskTransitionActionType.NOOP
    assert unrelated_plan.actions[0].task_public_id is None
    assert unrelated_plan.actions[0].reason == "UNRELATED"


def test_transition_plan_output_uses_public_ids_without_internal_owner_ids():
    task = _candidate(owner_id="internal-user-id-2")
    service = FollowUpTaskTransitionPlanService()

    plan = service.plan(
        FollowUpTaskReconciliationDecision(
            decision="COMPLETE",
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=0.94,
            evidence_terms=("预算已经通过",),
        ),
        _candidate_set(task, activity_owner_id="internal-user-id-2"),
    )

    payload = plan.to_dict()
    assert payload["actions"][0]["task_public_id"] == task.public_id
    assert "owner_id" not in str(payload)
    assert "internal-user-id-2" not in str(payload)


def test_transition_plan_can_be_built_from_semantic_match_result():
    task = _candidate()
    decision = FollowUpTaskReconciliationDecision(
        decision="COMPLETE",
        task_public_id=task.public_id,
        candidate_public_ids=(task.public_id,),
        confidence=0.94,
        evidence_terms=("预算已经通过",),
    )
    match_result = TaskReconciliationSemanticMatchResult(
        decision=decision,
        candidate_set=_candidate_set(task),
        source="langchain_structured_output",
        referenced_source_public_ids=("act_22222222222222222222222222222222",),
    )
    service = FollowUpTaskTransitionPlanService()

    plan = service.plan_from_match_result(match_result)

    assert plan.plan_source == "langchain_structured_output"
    assert plan.actions[0].source_activity_public_id == "act_22222222222222222222222222222222"
    assert plan.actions[0].executable is True
