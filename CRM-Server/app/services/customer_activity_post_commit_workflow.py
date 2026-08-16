"""Post-commit workflow for customer activity side effects.

This workflow is the single business orchestration entrypoint after a customer
activity has been committed. Channels such as web pages, Agent tools, and future
IM integrations should create/update the activity first, then invoke this
workflow instead of calling lower-level task services directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.core.database import SessionLocal
from app.crud.customer_activity import customer_activity_crud
from app.crud.sales_commitment import (
    follow_up_task_confirmation_case_crud,
    follow_up_task_crud,
    follow_up_task_transition_policy_decision_log_crud,
)
from app.models.agent import AgentWorkflowActionStatus
from app.models.sales_commitment import (
    FollowUpTaskConfirmationDeliveryPurpose,
    FollowUpTaskSourceType,
)
from app.services.agent import workflow_action_ledger
from app.services.customer_activity_ai.checkpointer import customer_activity_checkpoint_saver
from app.services.customer_activity_revision_fence import (
    CustomerActivityRevisionFence,
    CustomerActivityRevisionFenceReason,
    CustomerActivityRevisionFenceResult,
    customer_activity_revision_fence,
)
from app.services.follow_up_confirmation_delivery_workflow import (
    ConfirmationDeliveryInput,
    follow_up_confirmation_delivery_workflow,
)
from app.services.follow_up_task_confirmation_cleanup_service import (
    FollowUpTaskConfirmationCancelReason,
    FollowUpTaskConfirmationCleanupService,
    follow_up_task_confirmation_cleanup_service,
)
from app.services.follow_up_task_confirmation_service import follow_up_task_confirmation_service
from app.services.follow_up_task_projection_service import follow_up_task_projection_service
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.follow_up_task_transition_execution_service import follow_up_task_transition_execution_service
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionAction,
    FollowUpTaskTransitionActionType,
    FollowUpTaskTransitionPlan,
    follow_up_task_transition_plan_service,
)
from app.services.follow_up_task_transition_policy_service import follow_up_task_transition_policy_service
from app.services.task_reconciliation_semantic_matcher import task_reconciliation_semantic_matcher

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer_activity import CustomerActivity
    from app.models.sales_commitment import FollowUpTask, FollowUpTaskConfirmationCase
    from app.services.follow_up_task_confirmation_service import FollowUpTaskConfirmationCaseResult
    from app.services.follow_up_task_projection_service import FollowUpTaskProjectionResult
    from app.services.follow_up_task_transition_execution_service import FollowUpTaskTransitionExecutionResult
    from app.services.follow_up_task_transition_policy_service import FollowUpTaskTransitionPolicyResult
    from app.services.task_reconciliation_semantic_matcher import TaskReconciliationSemanticMatchResult


logger = logging.getLogger(__name__)


def merge_post_commit_events(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [*left, *right]


def merge_revision_fence_failures(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [*left, *right]


class CustomerActivityPostCommitSkipReason:
    ACTIVITY_NOT_FOUND = "ACTIVITY_NOT_FOUND"
    ACTIVITY_MISSING_CUSTOMER = "ACTIVITY_MISSING_CUSTOMER"
    ACTIVITY_MISSING_OWNER = "ACTIVITY_MISSING_OWNER"
    RECONCILIATION_UNAVAILABLE = "RECONCILIATION_UNAVAILABLE"
    SUPERSEDED_ACTIVITY_REVISION = "SUPERSEDED_ACTIVITY_REVISION"


class CustomerActivityPostCommitState(TypedDict, total=False):
    activity_id: int
    team_id: int
    expected_activity_revision: int
    trigger_type: str
    actor_id: str | None
    run_id: str
    activity: dict[str, Any]
    projection_result: dict[str, Any] | None
    match_result: dict[str, Any] | None
    transition_plan: dict[str, Any] | None
    policy_results: list[dict[str, Any]]
    execution_results: list[dict[str, Any]]
    confirmation_cases: list[dict[str, Any]]
    confirmation_deliveries: list[dict[str, Any]]
    post_commit: dict[str, Any]
    skip_reason: str | None
    error_message: str | None
    revision_fence_failures: Annotated[list[dict[str, Any]], merge_revision_fence_failures]
    events: Annotated[list[dict[str, Any]], merge_post_commit_events]


class _CompiledPostCommitGraph(Protocol):
    async def ainvoke(
        self,
        state: CustomerActivityPostCommitState,
        config: dict[str, Any],
    ) -> CustomerActivityPostCommitState: ...


class _ProjectionService(Protocol):
    def run_activity_projection(
        self,
        db: Session,
        *,
        activity_id: int,
        team_id: int,
        trigger_type: str,
        actor_id: str | None = None,
        activity_snapshot: CustomerActivity | None = None,
        commit: bool = True,
    ) -> FollowUpTaskProjectionResult: ...


class _SemanticMatcher(Protocol):
    async def match_activity(
        self,
        db: Session,
        *,
        team_id: int,
        activity_id: int,
        include_cross_owner: bool = False,
    ) -> TaskReconciliationSemanticMatchResult: ...


class _TransitionPlanService(Protocol):
    def plan_from_match_result(
        self,
        match_result: TaskReconciliationSemanticMatchResult,
        *,
        activity_owner_id: str | None = None,
        source_activity_public_id: str | None = None,
        plan_source: str | None = None,
    ) -> FollowUpTaskTransitionPlan: ...


class _TransitionPolicyService(Protocol):
    def is_auto_transition_allowed(
        self,
        db: Session,
        *,
        team_id: int,
        owner_id: str | None,
        action: str | None,
    ) -> FollowUpTaskTransitionPolicyResult: ...


class _TransitionExecutionService(Protocol):
    def execute_plan(
        self,
        db: Session,
        *,
        team_id: int,
        plan: FollowUpTaskTransitionPlan,
        actor_id: str | None,
        expected_owner_id: str | None = None,
        enabled: bool = False,
        commit: bool = True,
    ) -> list[FollowUpTaskTransitionExecutionResult]: ...


class _ConfirmationService(Protocol):
    def create_case_from_plan_action(
        self,
        db: Session,
        *,
        team_id: int,
        task: FollowUpTask,
        plan: FollowUpTaskTransitionPlan,
        action: FollowUpTaskTransitionAction,
        actor_id: str,
        source_activity_id: int | None = None,
        source_activity_revision: int | None = None,
        source_public_id: str | None = None,
        commit: bool = True,
    ) -> FollowUpTaskConfirmationCaseResult: ...


class _ConfirmationDeliveryWorkflow(Protocol):
    async def run(self, request: ConfirmationDeliveryInput) -> dict[str, Any]: ...


class _ConfirmationCaseCrud(Protocol):
    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int | None = None,
    ) -> FollowUpTaskConfirmationCase | None: ...


class _FollowUpTaskCrud(Protocol):
    def get_by_public_id(self, db: Session, public_id: str, team_id: int | None = None) -> FollowUpTask | None: ...


class _PolicyDecisionLogCrud(Protocol):
    def record_result(
        self,
        db: Session,
        *,
        policy_result: dict[str, Any],
        owner_id: str | None,
        actor_id: str | None = None,
        task: FollowUpTask | None = None,
        source_type: str | None = None,
        source_activity_id: int | None = None,
        source_public_id: str | None = None,
        context_json: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> object: ...


@dataclass(frozen=True)
class _PolicyDecision:
    action: dict[str, Any]
    task_public_id: str | None
    task_owner_id: str | None
    allowed: bool
    reason: str
    policy_result: dict[str, Any] | None = None
    task_found: bool = False


class CustomerActivityPostCommitWorkflow:
    """Coordinates all post-commit side effects for customer activities."""

    def __init__(
        self,
        *,
        projection_service: _ProjectionService = follow_up_task_projection_service,
        matcher: _SemanticMatcher = task_reconciliation_semantic_matcher,
        plan_service: _TransitionPlanService = follow_up_task_transition_plan_service,
        policy_service: _TransitionPolicyService = follow_up_task_transition_policy_service,
        execution_service: _TransitionExecutionService = follow_up_task_transition_execution_service,
        confirmation_service: _ConfirmationService = follow_up_task_confirmation_service,
        confirmation_case_crud: _ConfirmationCaseCrud = follow_up_task_confirmation_case_crud,
        task_crud: _FollowUpTaskCrud = follow_up_task_crud,
        policy_log_crud: _PolicyDecisionLogCrud = follow_up_task_transition_policy_decision_log_crud,
        delivery_workflow: _ConfirmationDeliveryWorkflow = follow_up_confirmation_delivery_workflow,
        revision_fence: CustomerActivityRevisionFence = customer_activity_revision_fence,
        confirmation_cleanup_service: FollowUpTaskConfirmationCleanupService = (
            follow_up_task_confirmation_cleanup_service
        ),
        checkpointer: object | None = customer_activity_checkpoint_saver,
    ) -> None:
        self.projection_service = projection_service
        self.matcher = matcher
        self.plan_service = plan_service
        self.policy_service = policy_service
        self.execution_service = execution_service
        self.confirmation_service = confirmation_service
        self.confirmation_case_crud = confirmation_case_crud
        self.task_crud = task_crud
        self.policy_log_crud = policy_log_crud
        self.delivery_workflow = delivery_workflow
        self.revision_fence = revision_fence
        self.confirmation_cleanup_service = confirmation_cleanup_service
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer: object | None) -> _CompiledPostCommitGraph:
        graph = StateGraph(CustomerActivityPostCommitState)
        db_retry = RetryPolicy(initial_interval=0.2, backoff_factor=2.0, max_interval=2.0, max_attempts=3)

        graph.add_node("load_activity", self._load_activity, retry_policy=db_retry)
        graph.add_node("project_next_step", self._project_next_step)
        graph.add_node("match_and_plan_historical_tasks", self._match_and_plan_historical_tasks)
        graph.add_node("apply_transition_policy", self._apply_transition_policy)
        graph.add_node("execute_transition", self._execute_transition)
        graph.add_node("create_confirmation_cases", self._create_confirmation_cases)
        graph.add_node("schedule_confirmation_deliveries", self._schedule_confirmation_deliveries)
        graph.add_node("build_post_commit_outcome", self._build_post_commit_outcome)

        graph.add_edge(START, "load_activity")
        graph.add_conditional_edges(
            "load_activity",
            self._route_after_load_activity,
            {
                "project_next_step": "project_next_step",
                "match_and_plan_historical_tasks": "match_and_plan_historical_tasks",
                "finish": "build_post_commit_outcome",
            },
        )
        graph.add_edge(["project_next_step", "match_and_plan_historical_tasks"], "apply_transition_policy")
        graph.add_edge("apply_transition_policy", "execute_transition")
        graph.add_edge("execute_transition", "create_confirmation_cases")
        graph.add_edge("create_confirmation_cases", "schedule_confirmation_deliveries")
        graph.add_edge("schedule_confirmation_deliveries", "build_post_commit_outcome")
        graph.add_edge("build_post_commit_outcome", END)
        return graph.compile(checkpointer=checkpointer)

    async def run(
        self,
        *,
        activity_id: int,
        team_id: int,
        expected_activity_revision: int,
        trigger_type: str,
        actor_id: str | None = None,
        run_id: str | None = None,
        thread_id: str | None = None,
    ) -> CustomerActivityPostCommitState:
        resolved_run_id = run_id or uuid4().hex
        resolved_thread_id = thread_id or (
            f"customer_activity_post_commit:{activity_id}:{trigger_type}:{resolved_run_id}"
        )
        state: CustomerActivityPostCommitState = {
            "activity_id": activity_id,
            "team_id": team_id,
            "expected_activity_revision": expected_activity_revision,
            "trigger_type": trigger_type,
            "actor_id": actor_id,
            "run_id": resolved_run_id,
            "events": [{"event": "post_commit_workflow_started", "run_id": resolved_run_id}],
        }
        return await self._graph.ainvoke(
            state,
            {
                "configurable": {
                    "thread_id": resolved_thread_id,
                    "checkpoint_ns": "customer_activity_post_commit",
                },
                "metadata": {
                    "activity_id": activity_id,
                    "team_id": team_id,
                    "expected_activity_revision": expected_activity_revision,
                    "trigger_type": trigger_type,
                    "actor_id": actor_id,
                    "run_id": resolved_run_id,
                },
            },
        )

    def _load_activity(self, state: CustomerActivityPostCommitState) -> CustomerActivityPostCommitState:
        db = SessionLocal()
        try:
            activity = customer_activity_crud.get_by_id(db, state["activity_id"], state["team_id"])
            if activity is None:
                return {
                    "skip_reason": CustomerActivityPostCommitSkipReason.ACTIVITY_NOT_FOUND,
                    "events": [{"event": "activity_not_found", "activity_id": state["activity_id"]}],
                }
            actual_revision = int(activity.post_commit_revision or 1)
            if actual_revision != state["expected_activity_revision"]:
                return {
                    "skip_reason": CustomerActivityPostCommitSkipReason.SUPERSEDED_ACTIVITY_REVISION,
                    **self._revision_fence_failure(
                        state,
                        node="load_activity",
                        fence=CustomerActivityRevisionFenceResult(
                            activity=activity,
                            expected_revision=state["expected_activity_revision"],
                            actual_revision=actual_revision,
                            reason=CustomerActivityPostCommitSkipReason.SUPERSEDED_ACTIVITY_REVISION,
                        ),
                    ),
                }
            return {
                "activity": _activity_payload(activity),
                "events": [{"event": "activity_loaded", "activity_id": activity.id}],
            }
        finally:
            db.close()

    def _route_after_load_activity(self, state: CustomerActivityPostCommitState) -> str | list[str]:
        if state.get("skip_reason"):
            return "finish"
        return ["project_next_step", "match_and_plan_historical_tasks"]

    def _project_next_step(self, state: CustomerActivityPostCommitState) -> CustomerActivityPostCommitState:
        db = SessionLocal()
        try:
            fence = self._lock_expected_revision(db, state)
            if not fence.allowed:
                self._record_fenced_system_action(
                    db,
                    state=state,
                    action_type="project_next_follow_up_tasks",
                    source_type=workflow_action_ledger.SOURCE_POST_COMMIT_PROJECTION,
                    fence=fence,
                )
                db.commit()
                return {
                    "projection_result": {
                        "success": False,
                        "skip_reason": fence.reason,
                        "expected_activity_revision": fence.expected_revision,
                        "actual_activity_revision": fence.actual_revision,
                    },
                    **self._revision_fence_failure(state, node="project_next_step", fence=fence),
                }
            try:
                result = self.projection_service.run_activity_projection(
                    db,
                    activity_id=state["activity_id"],
                    team_id=state["team_id"],
                    trigger_type=state["trigger_type"],
                    actor_id=state.get("actor_id"),
                    activity_snapshot=fence.activity,
                    commit=False,
                )
            except Exception as exc:
                logger.exception("客户活动后提交任务投影失败: activity_id=%s", state["activity_id"])
                _record_post_commit_system_action(
                    db,
                    state=state,
                    action_type="project_next_follow_up_tasks",
                    source_type=workflow_action_ledger.SOURCE_POST_COMMIT_PROJECTION,
                    status=AgentWorkflowActionStatus.FAILED,
                    result={"success": False, "error": str(exc)},
                    reason=str(exc)[:300],
                    commit=False,
                )
                db.commit()
                return {
                    "projection_result": {"success": False, "error": str(exc)},
                    "events": [{"event": "next_step_projection_failed", "error": str(exc)[:300]}],
                }
            projection_payload = _projection_payload(result)
            _record_post_commit_system_action(
                db,
                state=state,
                action_type="project_next_follow_up_tasks",
                source_type=workflow_action_ledger.SOURCE_POST_COMMIT_PROJECTION,
                status=AgentWorkflowActionStatus.EXECUTED
                if result.projection_run_status != "FAILED"
                else AgentWorkflowActionStatus.FAILED,
                payload={
                    "activity_id": state["activity_id"],
                    "trigger_type": state["trigger_type"],
                },
                result=projection_payload,
                reason=result.skip_reason or result.error_message,
                commit=False,
            )
            db.commit()
            return {
                "projection_result": projection_payload,
                "events": [
                    {
                        "event": "next_step_projected",
                        "status": result.projection_run_status,
                        "skip_reason": result.skip_reason,
                    }
                ],
            }
        finally:
            db.close()

    async def _match_and_plan_historical_tasks(
        self,
        state: CustomerActivityPostCommitState,
    ) -> CustomerActivityPostCommitState:
        activity = state.get("activity") or {}
        if not activity.get("customer_id"):
            return {
                "skip_reason": CustomerActivityPostCommitSkipReason.ACTIVITY_MISSING_CUSTOMER,
                "events": [{"event": "historical_reconciliation_skipped", "reason": "ACTIVITY_MISSING_CUSTOMER"}],
            }
        if not activity.get("owner_id"):
            return {
                "skip_reason": CustomerActivityPostCommitSkipReason.ACTIVITY_MISSING_OWNER,
                "events": [{"event": "historical_reconciliation_skipped", "reason": "ACTIVITY_MISSING_OWNER"}],
            }

        db = SessionLocal()
        try:
            try:
                match_result = await self.matcher.match_activity(
                    db,
                    team_id=state["team_id"],
                    activity_id=state["activity_id"],
                    include_cross_owner=False,
                )
                plan = self.plan_service.plan_from_match_result(
                    match_result,
                    activity_owner_id=str(activity.get("owner_id") or ""),
                    source_activity_public_id=activity.get("public_id"),
                    plan_source="customer_activity_post_commit",
                )
            except ValueError as exc:
                _record_post_commit_system_action(
                    db,
                    state=state,
                    action_type="reconcile_historical_follow_up_tasks",
                    source_type=workflow_action_ledger.SOURCE_POST_COMMIT_RECONCILIATION,
                    status=AgentWorkflowActionStatus.BLOCKED,
                    result={"success": False, "error": str(exc)},
                    reason=str(exc)[:300],
                )
                return {
                    "skip_reason": CustomerActivityPostCommitSkipReason.RECONCILIATION_UNAVAILABLE,
                    "error_message": str(exc),
                    "events": [{"event": "historical_reconciliation_skipped", "reason": str(exc)[:300]}],
                }
            except Exception as exc:
                logger.exception("客户活动后提交历史任务对账失败: activity_id=%s", state["activity_id"])
                _record_post_commit_system_action(
                    db,
                    state=state,
                    action_type="reconcile_historical_follow_up_tasks",
                    source_type=workflow_action_ledger.SOURCE_POST_COMMIT_RECONCILIATION,
                    status=AgentWorkflowActionStatus.FAILED,
                    result={"success": False, "error": str(exc)},
                    reason=str(exc)[:300],
                )
                return {
                    "skip_reason": CustomerActivityPostCommitSkipReason.RECONCILIATION_UNAVAILABLE,
                    "error_message": str(exc),
                    "events": [{"event": "historical_reconciliation_failed", "error": str(exc)[:300]}],
                }
            match_payload = match_result.to_dict()
            plan_payload = plan.to_dict()
            fence = self._lock_expected_revision(db, state)
            if not fence.allowed:
                self._record_fenced_system_action(
                    db,
                    state=state,
                    action_type="reconcile_historical_follow_up_tasks",
                    source_type=workflow_action_ledger.SOURCE_POST_COMMIT_RECONCILIATION,
                    fence=fence,
                )
                db.commit()
                return {
                    "match_result": None,
                    "transition_plan": None,
                    **self._revision_fence_failure(
                        state,
                        node="match_and_plan_historical_tasks",
                        fence=fence,
                    ),
                }
            _record_post_commit_system_action(
                db,
                state=state,
                action_type="reconcile_historical_follow_up_tasks",
                source_type=workflow_action_ledger.SOURCE_POST_COMMIT_RECONCILIATION,
                status=AgentWorkflowActionStatus.EXECUTED,
                payload={
                    "activity_id": state["activity_id"],
                    "include_cross_owner": False,
                },
                result={
                    "match_result": match_payload,
                    "transition_plan": plan_payload,
                },
                reason=plan.decision.decision,
                commit=False,
            )
            db.commit()
            return {
                "match_result": match_payload,
                "transition_plan": plan_payload,
                "events": [
                    {
                        "event": "historical_tasks_matched",
                        "decision": plan.decision.decision,
                        "action_count": len(plan.actions),
                    }
                ],
            }
        finally:
            db.close()

    def _apply_transition_policy(self, state: CustomerActivityPostCommitState) -> CustomerActivityPostCommitState:
        if state.get("revision_fence_failures"):
            return self._skip_after_revision_fence(state, "transition_policy_skipped") | {"policy_results": []}
        plan_payload = state.get("transition_plan")
        if not plan_payload:
            return {"policy_results": [], "events": [{"event": "transition_policy_skipped"}]}

        db = SessionLocal()
        try:
            fence = self._lock_expected_revision(db, state)
            if not fence.allowed:
                db.rollback()
                return {
                    "policy_results": [],
                    "skip_reason": self._skip_reason_for_fence(fence),
                    **self._revision_fence_failure(state, node="apply_transition_policy", fence=fence),
                }
            policy_results: list[dict[str, Any]] = []
            for action_payload in plan_payload.get("actions") or []:
                decision = self._policy_decision_for_action(db, state=state, action_payload=action_payload)
                policy_results.append(_policy_decision_payload(decision))
                if decision.policy_result is not None:
                    task = self._task_by_public_id(db, state["team_id"], decision.task_public_id)
                    self.policy_log_crud.record_result(
                        db,
                        policy_result=decision.policy_result,
                        owner_id=decision.task_owner_id,
                        actor_id=state.get("actor_id"),
                        task=task,
                        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
                        source_activity_id=state["activity_id"],
                        source_public_id=(state.get("activity") or {}).get("public_id"),
                        context_json={
                            "workflow": "CustomerActivityPostCommitWorkflow",
                            "run_id": state.get("run_id"),
                            "trigger_type": state.get("trigger_type"),
                            "action": action_payload,
                            "plan": plan_payload,
                        },
                        commit=False,
                    )
            db.commit()
            return {
                "policy_results": policy_results,
                "events": [{"event": "transition_policy_applied", "policy_count": len(policy_results)}],
            }
        finally:
            db.close()

    def _execute_transition(self, state: CustomerActivityPostCommitState) -> CustomerActivityPostCommitState:
        if state.get("revision_fence_failures"):
            return self._skip_after_revision_fence(state, "transition_execution_skipped") | {
                "execution_results": []
            }
        plan_payload = state.get("transition_plan")
        if not plan_payload:
            return {"execution_results": [], "events": [{"event": "transition_execution_skipped"}]}

        plan = _plan_from_payload(plan_payload)
        allowed = _plan_is_allowed_by_policy(state.get("policy_results") or [])
        db = SessionLocal()
        try:
            fence = self._lock_expected_revision(db, state)
            if not fence.allowed:
                db.rollback()
                return {
                    "execution_results": [],
                    "skip_reason": self._skip_reason_for_fence(fence),
                    **self._revision_fence_failure(state, node="execute_transition", fence=fence),
                }
            results = self.execution_service.execute_plan(
                db,
                team_id=state["team_id"],
                plan=plan,
                actor_id=state.get("actor_id"),
                expected_owner_id=(state.get("activity") or {}).get("owner_id"),
                enabled=allowed,
                commit=False,
            )
            db.commit()
            return {
                "execution_results": [result.to_dict() for result in results],
                "events": [
                    {
                        "event": "transition_execution_finished",
                        "enabled": allowed,
                        "result_count": len(results),
                    }
                ],
            }
        finally:
            db.close()

    def _create_confirmation_cases(self, state: CustomerActivityPostCommitState) -> CustomerActivityPostCommitState:
        if state.get("revision_fence_failures"):
            return self._skip_after_revision_fence(state, "confirmation_cases_skipped") | {
                "confirmation_cases": []
            }
        plan_payload = state.get("transition_plan")
        if not plan_payload:
            return {"confirmation_cases": [], "events": [{"event": "confirmation_cases_skipped"}]}

        policy_results_by_task = {
            result.get("task_public_id"): result
            for result in state.get("policy_results") or []
            if result.get("task_public_id")
        }
        execution_results_by_task = {
            result.get("task_public_id"): result
            for result in state.get("execution_results") or []
            if result.get("task_public_id")
        }
        plan = _plan_from_payload(plan_payload)
        cases: list[dict[str, Any]] = []
        db = SessionLocal()
        try:
            fence = self._lock_expected_revision(db, state)
            if not fence.allowed:
                db.rollback()
                return {
                    "confirmation_cases": [],
                    "skip_reason": self._skip_reason_for_fence(fence),
                    **self._revision_fence_failure(state, node="create_confirmation_cases", fence=fence),
                }
            for action in plan.actions:
                confirmation_action = self._confirmation_action(
                    action,
                    policy_results_by_task=policy_results_by_task,
                    execution_results_by_task=execution_results_by_task,
                )
                if confirmation_action is None or not confirmation_action.task_public_id:
                    continue
                task = self.task_crud.get_by_public_id(
                    db,
                    confirmation_action.task_public_id,
                    team_id=state["team_id"],
                )
                if task is None:
                    cases.append(
                        {
                            "task_public_id": confirmation_action.task_public_id,
                            "status": "SKIPPED",
                            "skip_reason": "TASK_NOT_FOUND",
                        }
                    )
                    continue
                confirmation_plan = _plan_with_single_action(plan, confirmation_action)
                result = self.confirmation_service.create_case_from_plan_action(
                    db,
                    team_id=state["team_id"],
                    task=task,
                    plan=confirmation_plan,
                    action=confirmation_action,
                    actor_id=state.get("actor_id") or task.owner_id,
                    source_activity_id=state["activity_id"],
                    source_activity_revision=state["expected_activity_revision"],
                    source_public_id=(state.get("activity") or {}).get("public_id"),
                    commit=False,
                )
                cases.append(
                    {
                        "case_public_id": result.case.public_id,
                        "task_public_id": task.public_id,
                        "created": result.created,
                        "confirmation_hash": result.confirmation_hash,
                        "suggested_action": result.case.suggested_action,
                        "owner_id": result.case.owner_id,
                    }
                )
            db.commit()
            return {
                "confirmation_cases": cases,
                "events": [{"event": "confirmation_cases_created", "case_count": len(cases)}],
            }
        finally:
            db.close()

    async def _schedule_confirmation_deliveries(
        self,
        state: CustomerActivityPostCommitState,
    ) -> CustomerActivityPostCommitState:
        if state.get("revision_fence_failures"):
            return self._skip_after_revision_fence(state, "confirmation_deliveries_skipped") | {
                "confirmation_deliveries": []
            }
        delivery_targets: list[dict[str, Any]] = []
        deliveries: list[dict[str, Any]] = []
        db = SessionLocal()
        try:
            fence = self._lock_expected_revision(db, state)
            if not fence.allowed:
                skip_reason = self._skip_reason_for_fence(fence)
                cleanup = self.confirmation_cleanup_service.cancel_pending_cases_for_source_activity(
                    db,
                    team_id=state["team_id"],
                    source_activity_id=state["activity_id"],
                    actor_id=state.get("actor_id"),
                    reason=self._confirmation_cancel_reason_for_fence(fence),
                    commit=False,
                )
                db.commit()
                return {
                    "confirmation_cases": [],
                    "confirmation_deliveries": [
                        {
                            "case_public_id": case.get("case_public_id"),
                            "status": "SKIPPED",
                            "reason_code": skip_reason,
                        }
                        for case in state.get("confirmation_cases") or []
                        if isinstance(case, dict) and case.get("case_public_id")
                    ],
                    "skip_reason": skip_reason,
                    **self._revision_fence_failure(
                        state,
                        node="schedule_confirmation_deliveries",
                        fence=fence,
                        extra={"cancelled_case_count": cleanup.cancelled_count},
                    ),
                }
            for case_payload in state.get("confirmation_cases") or []:
                case_public_id = (
                    case_payload.get("case_public_id")
                    if isinstance(case_payload, dict)
                    else None
                )
                if not case_public_id:
                    continue
                persisted_case = self.confirmation_case_crud.get_by_public_id(
                    db,
                    public_id=str(case_public_id),
                    team_id=state["team_id"],
                )
                if persisted_case is None:
                    deliveries.append(
                        {
                            "delivery_public_id": None,
                            "case_public_id": str(case_public_id),
                            "channel": "web",
                            "provider": "confirmation_center",
                            "purpose": FollowUpTaskConfirmationDeliveryPurpose.INBOX_VISIBILITY,
                            "status": "SKIPPED",
                            "reason_code": "CASE_NOT_FOUND",
                            "provider_message_id": None,
                        }
                    )
                    continue
                delivery_targets.append(
                    {
                        "case_public_id": str(persisted_case.public_id),
                        "owner_id": str(persisted_case.owner_id),
                        "source_activity_id": persisted_case.source_activity_id,
                        "source_activity_revision": persisted_case.source_activity_revision,
                    }
                )
            db.commit()
        finally:
            db.close()
        for target in delivery_targets:
            case_public_id = target["case_public_id"]
            result = await self.delivery_workflow.run(
                ConfirmationDeliveryInput(
                    case_public_id=str(case_public_id),
                    team_id=state["team_id"],
                    owner_id=target["owner_id"],
                    channel="web",
                    provider="confirmation_center",
                    origin_turn_id=f"activity:{state['activity_id']}",
                    origin_message_id=state["activity_id"],
                    source_activity_id=target["source_activity_id"],
                    expected_activity_revision=target["source_activity_revision"],
                )
            )
            deliveries.append(
                {
                    "delivery_public_id": result.get("delivery_public_id"),
                    "case_public_id": str(case_public_id),
                    "channel": "web",
                    "provider": "confirmation_center",
                    "purpose": FollowUpTaskConfirmationDeliveryPurpose.INBOX_VISIBILITY,
                    "status": result.get("status"),
                    "reason_code": result.get("reason_code"),
                    "provider_message_id": result.get("provider_message_id"),
                }
            )
        return {
            "confirmation_deliveries": deliveries,
            "events": [
                {
                    "event": "confirmation_deliveries_scheduled",
                    "delivery_count": len(deliveries),
                    "sent_count": sum(1 for item in deliveries if item.get("status") == "SENT"),
                }
            ],
        }

    def _lock_expected_revision(
        self,
        db: Session,
        state: CustomerActivityPostCommitState,
    ) -> CustomerActivityRevisionFenceResult:
        return self.revision_fence.lock_for_mutation(
            db,
            team_id=state["team_id"],
            activity_id=state["activity_id"],
            expected_revision=state["expected_activity_revision"],
        )

    @staticmethod
    def _revision_fence_failure(
        state: CustomerActivityPostCommitState,
        *,
        node: str,
        fence: CustomerActivityRevisionFenceResult,
        extra: dict[str, Any] | None = None,
    ) -> CustomerActivityPostCommitState:
        payload = {
            "node": node,
            "reason": fence.reason,
            "activity_id": state["activity_id"],
            "expected_activity_revision": fence.expected_revision,
            "actual_activity_revision": fence.actual_revision,
            **(extra or {}),
        }
        return {
            "revision_fence_failures": [payload],
            "events": [{"event": "activity_revision_fenced", **payload}],
        }

    @staticmethod
    def _skip_reason_for_fence(fence: CustomerActivityRevisionFenceResult) -> str:
        if fence.reason == CustomerActivityRevisionFenceReason.ACTIVITY_NOT_FOUND:
            return CustomerActivityPostCommitSkipReason.ACTIVITY_NOT_FOUND
        return CustomerActivityPostCommitSkipReason.SUPERSEDED_ACTIVITY_REVISION

    @staticmethod
    def _confirmation_cancel_reason_for_fence(fence: CustomerActivityRevisionFenceResult) -> str:
        if fence.reason == CustomerActivityRevisionFenceReason.ACTIVITY_NOT_FOUND:
            return FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_DELETED
        return FollowUpTaskConfirmationCancelReason.SOURCE_ACTIVITY_REVISION_SUPERSEDED

    @classmethod
    def _skip_after_revision_fence(
        cls,
        state: CustomerActivityPostCommitState,
        event: str,
    ) -> CustomerActivityPostCommitState:
        failure_reasons = {
            str(failure.get("reason"))
            for failure in state.get("revision_fence_failures") or []
            if isinstance(failure, dict) and failure.get("reason")
        }
        if CustomerActivityRevisionFenceReason.ACTIVITY_NOT_FOUND in failure_reasons:
            reason = CustomerActivityPostCommitSkipReason.ACTIVITY_NOT_FOUND
        elif CustomerActivityRevisionFenceReason.SUPERSEDED_ACTIVITY_REVISION in failure_reasons:
            reason = CustomerActivityPostCommitSkipReason.SUPERSEDED_ACTIVITY_REVISION
        else:
            reason = str(
                state.get("skip_reason")
                or CustomerActivityPostCommitSkipReason.SUPERSEDED_ACTIVITY_REVISION
            )
        return {
            "skip_reason": reason,
            "events": [{"event": event, "reason": reason}],
        }

    def _record_fenced_system_action(
        self,
        db: Session,
        *,
        state: CustomerActivityPostCommitState,
        action_type: str,
        source_type: str,
        fence: CustomerActivityRevisionFenceResult,
    ) -> None:
        _record_post_commit_system_action(
            db,
            state=state,
            action_type=action_type,
            source_type=source_type,
            status=AgentWorkflowActionStatus.BLOCKED,
            result={
                "success": False,
                "skip_reason": fence.reason,
                "expected_activity_revision": fence.expected_revision,
                "actual_activity_revision": fence.actual_revision,
            },
            reason=fence.reason,
            commit=False,
        )

    def _build_post_commit_outcome(self, state: CustomerActivityPostCommitState) -> CustomerActivityPostCommitState:
        confirmation_cases = [
            case
            for case in state.get("confirmation_cases") or []
            if isinstance(case, dict) and case.get("case_public_id")
        ]
        confirmation_case_public_ids = [
            str(case["case_public_id"])
            for case in confirmation_cases
        ]
        confirmation_deliveries = list(state.get("confirmation_deliveries") or [])
        post_commit = {
            "needs_user_confirmation": bool(confirmation_case_public_ids),
            "confirmation_case_public_ids": confirmation_case_public_ids,
            "confirmation_cases": confirmation_cases,
            "confirmation_deliveries": confirmation_deliveries,
            "created_confirmation_case_count": sum(1 for case in confirmation_cases if case.get("created") is True),
            "prompt_policy": {
                "prompt_scope": "current_activity",
                "delivery": "durable_confirmation_inbox",
            },
        }
        return {
            "post_commit": post_commit,
            "events": [
                {
                    "event": "post_commit_outcome_built",
                    "needs_user_confirmation": post_commit["needs_user_confirmation"],
                    "confirmation_case_count": len(confirmation_case_public_ids),
                }
            ],
        }

    def _policy_decision_for_action(
        self,
        db: Session,
        *,
        state: CustomerActivityPostCommitState,
        action_payload: dict[str, Any],
    ) -> _PolicyDecision:
        task_public_id = action_payload.get("task_public_id")
        if not action_payload.get("executable"):
            return _PolicyDecision(
                action=action_payload,
                task_public_id=task_public_id,
                task_owner_id=None,
                allowed=False,
                reason="ACTION_NOT_EXECUTABLE",
            )
        if not task_public_id:
            return _PolicyDecision(
                action=action_payload,
                task_public_id=None,
                task_owner_id=None,
                allowed=False,
                reason="TASK_PUBLIC_ID_MISSING",
            )

        task = self._task_by_public_id(db, state["team_id"], task_public_id)
        if task is None:
            return _PolicyDecision(
                action=action_payload,
                task_public_id=task_public_id,
                task_owner_id=None,
                allowed=False,
                reason="TASK_NOT_FOUND",
            )
        policy_result = self.policy_service.is_auto_transition_allowed(
            db,
            team_id=state["team_id"],
            owner_id=task.owner_id,
            action=action_payload.get("action"),
        )
        return _PolicyDecision(
            action=action_payload,
            task_public_id=task.public_id,
            task_owner_id=task.owner_id,
            allowed=policy_result.allowed,
            reason=policy_result.reason,
            policy_result=policy_result.to_dict(),
            task_found=True,
        )

    def _task_by_public_id(self, db: Session, team_id: int, public_id: str | None) -> FollowUpTask | None:
        if not public_id:
            return None
        return self.task_crud.get_by_public_id(db, public_id, team_id=team_id)

    def _confirmation_action(
        self,
        action: FollowUpTaskTransitionAction,
        *,
        policy_results_by_task: dict[str, dict[str, Any]],
        execution_results_by_task: dict[str, dict[str, Any]],
    ) -> FollowUpTaskTransitionAction | None:
        if action.requires_confirmation:
            return action
        if not action.executable or not action.task_public_id:
            return None

        execution = execution_results_by_task.get(action.task_public_id) or {}
        if execution.get("status") == "EXECUTED":
            return None

        policy = policy_results_by_task.get(action.task_public_id) or {}
        if policy.get("allowed") is True:
            return None
        forbid_reasons = tuple(
            dict.fromkeys(
                (
                    *action.forbid_auto_reasons,
                    policy.get("reason") or execution.get("skip_reason") or "AUTO_TRANSITION_NOT_EXECUTED",
                )
            )
        )
        return FollowUpTaskTransitionAction(
            action=FollowUpTaskTransitionActionType.ASK_CONFIRMATION,
            task_public_id=action.task_public_id,
            confidence=action.confidence,
            executable=False,
            requires_confirmation=True,
            proposed_due_at=action.proposed_due_at,
            reason="AUTO_TRANSITION_BLOCKED_BY_POLICY",
            forbid_auto_reasons=forbid_reasons,
            evidence_terms=action.evidence_terms,
            source_activity_public_id=action.source_activity_public_id,
        )


def _activity_payload(activity: CustomerActivity) -> dict[str, Any]:
    return {
        "id": activity.id,
        "public_id": getattr(activity, "public_id", None),
        "team_id": activity.team_id,
        "post_commit_revision": int(activity.post_commit_revision or 1),
        "customer_id": activity.customer_id,
        "owner_id": activity.owner_id,
        "creator_id": activity.creator_id,
        "activity_kind": activity.activity_kind,
        "title": activity.title,
        "source_content": activity.source_content,
        "summary": activity.summary,
        "next_action": activity.next_action,
        "next_follow_time": activity.next_follow_time.isoformat() if activity.next_follow_time else None,
        "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
    }


def _record_post_commit_system_action(
    db: Session,
    *,
    state: CustomerActivityPostCommitState,
    action_type: str,
    source_type: str,
    status: str,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    reason: str | None = None,
    commit: bool = True,
) -> None:
    activity = state.get("activity") or {}
    activity_id = state.get("activity_id")
    trigger_type = str(state.get("trigger_type") or "unknown")
    workflow_action_ledger.record_system_action(
        db,
        team_id=state["team_id"],
        user_id=_actor_id_as_int(state.get("actor_id")),
        workflow_id=_post_commit_workflow_id(activity_id, trigger_type),
        action_id=_post_commit_action_id(action_type, activity_id, trigger_type),
        action_type=action_type,
        source_type=source_type,
        status=status,
        target_type="customer",
        target_id=activity.get("customer_id") if isinstance(activity.get("customer_id"), int) else None,
        dependency={
            "depends_on": [],
            "parallel_group": "post_commit_activity_analysis",
            "join": "apply_transition_policy",
        },
        payload=payload
        or {
            "activity_id": activity_id,
            "activity_public_id": activity.get("public_id"),
            "trigger_type": state.get("trigger_type"),
        },
        result=result,
        reason=reason,
        commit=commit,
    )


def _actor_id_as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _post_commit_workflow_id(activity_id: object, trigger_type: str) -> str:
    return f"wf_pc_{activity_id}_{_stable_identifier_part(trigger_type)}"[:64]


def _post_commit_action_id(action_type: str, activity_id: object, trigger_type: str) -> str:
    prefix_by_action = {
        "project_next_follow_up_tasks": "proj",
        "reconcile_historical_follow_up_tasks": "recon",
    }
    prefix = prefix_by_action.get(action_type, "sys")
    trigger = _stable_identifier_part(trigger_type)
    return f"act_pc_{prefix}_{activity_id}_{trigger}"[:64]


def _stable_identifier_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower())
    return cleaned.strip("_") or "unknown"


def _projection_payload(result: FollowUpTaskProjectionResult) -> dict[str, Any]:
    return {
        "trigger_type": result.trigger_type,
        "source_type": result.source_type,
        "source_key": result.source_key,
        "input_snapshot_hash": result.input_snapshot_hash,
        "projection_hash": result.projection_hash,
        "skip_reason": result.skip_reason,
        "created_task_ids": result.created_task_ids,
        "updated_task_ids": result.updated_task_ids,
        "cancelled_task_ids": result.cancelled_task_ids,
        "created_commitment_ids": result.created_commitment_ids,
        "updated_commitment_ids": result.updated_commitment_ids,
        "projection_run_id": result.projection_run_id,
        "projection_run_status": result.projection_run_status,
        "error_message": result.error_message,
    }


def _policy_decision_payload(decision: _PolicyDecision) -> dict[str, Any]:
    return {
        "action": decision.action.get("action"),
        "task_public_id": decision.task_public_id,
        "task_owner_id": decision.task_owner_id,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "policy_result": decision.policy_result,
        "task_found": decision.task_found,
    }


def _plan_is_allowed_by_policy(policy_results: list[dict[str, Any]]) -> bool:
    executable_policy_results = [
        result
        for result in policy_results
        if result.get("task_found") and isinstance(result.get("policy_result"), dict)
    ]
    if not executable_policy_results:
        return False
    return all(result.get("allowed") is True for result in executable_policy_results)


def _plan_from_payload(payload: dict[str, Any]) -> FollowUpTaskTransitionPlan:
    decision_payload = payload.get("decision") or {}
    decision = FollowUpTaskReconciliationDecision(
        decision=str(decision_payload.get("decision") or "UNRELATED"),
        task_public_id=decision_payload.get("task_public_id"),
        candidate_public_ids=tuple(decision_payload.get("candidate_public_ids") or ()),
        confidence=float(decision_payload.get("confidence") or 0),
        needs_confirmation=bool(decision_payload.get("needs_confirmation") or False),
        proposed_due_at=decision_payload.get("proposed_due_at"),
        forbid_auto_reasons=tuple(decision_payload.get("forbid_auto_reasons") or ()),
        evidence_terms=tuple(decision_payload.get("evidence_terms") or ()),
        state_mutation_requested=bool(decision_payload.get("state_mutation_requested") or False),
    )
    actions = tuple(_action_from_payload(action) for action in payload.get("actions") or ())
    return FollowUpTaskTransitionPlan(
        decision=decision,
        actions=actions,
        plan_source=str(payload.get("plan_source") or "customer_activity_post_commit"),
        safety_failures=tuple(payload.get("safety_failures") or ()),
        state_mutation_requested=bool(payload.get("state_mutation_requested") or False),
    )


def _action_from_payload(payload: dict[str, Any]) -> FollowUpTaskTransitionAction:
    return FollowUpTaskTransitionAction(
        action=str(payload.get("action") or FollowUpTaskTransitionActionType.NOOP),
        task_public_id=payload.get("task_public_id"),
        confidence=float(payload.get("confidence") or 0),
        executable=bool(payload.get("executable") or False),
        requires_confirmation=bool(payload.get("requires_confirmation") or False),
        proposed_due_at=payload.get("proposed_due_at"),
        reason=payload.get("reason"),
        forbid_auto_reasons=tuple(payload.get("forbid_auto_reasons") or ()),
        evidence_terms=tuple(payload.get("evidence_terms") or ()),
        source_activity_public_id=payload.get("source_activity_public_id"),
    )


def _plan_with_single_action(
    plan: FollowUpTaskTransitionPlan,
    action: FollowUpTaskTransitionAction,
) -> FollowUpTaskTransitionPlan:
    return FollowUpTaskTransitionPlan(
        decision=plan.decision,
        actions=(action,),
        plan_source=plan.plan_source,
        safety_failures=tuple(dict.fromkeys((*plan.safety_failures, *action.forbid_auto_reasons))),
        state_mutation_requested=plan.state_mutation_requested,
    )


customer_activity_post_commit_workflow = CustomerActivityPostCommitWorkflow()
