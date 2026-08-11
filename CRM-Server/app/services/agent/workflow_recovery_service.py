"""Controlled recovery for failed Agent workflow actions."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.crud.agent import agent_session_crud, agent_workflow_action_crud
from app.models.agent import AgentWorkflowAction
from app.services.agent import action_workflow, workflow_action_ledger
from app.services.agent.root_runtime import AgentRootRuntime, agent_root_runtime
from app.services.agent.types import JSONDict
from app.services.agent.workflow_recovery_policy import (
    REASON_ALLOWED,
    evaluate_background_recovery_policy,
    normalized_safe_action_types,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkflowRecoveryDecision:
    workflow_id: str
    eligible: bool
    reason: str
    action_count: int
    retryable_action_count: int
    safe_action_count: int
    policy_reasons: dict[str, int]
    retryable_action_policies: list[dict[str, object]]


class AgentWorkflowRecoveryService:
    """Find and optionally replay safe failed Agent workflow work.

    The service deliberately does not interpret user text and does not execute
    CRM mutations itself. It classifies durable ledger actions, then delegates
    eligible workflow replay back to the root runtime so DAG dependencies,
    idempotency, and action status transitions remain centralized.
    """

    def __init__(self, *, runtime: AgentRootRuntime | None = None) -> None:
        self.runtime = runtime or agent_root_runtime

    async def recover_once(
        self,
        db: Session,
        *,
        limit: int | None = None,
        dry_run: bool | None = None,
        safe_action_types: Iterable[str] | None = None,
        team_id: int | None = None,
        user_id: int | None = None,
    ) -> JSONDict:
        settings = get_settings()
        batch_size = max(1, limit if limit is not None else settings.AGENT_WORKFLOW_RECOVERY_BATCH_SIZE)
        effective_dry_run = settings.AGENT_WORKFLOW_RECOVERY_DRY_RUN if dry_run is None else dry_run
        safe_actions = normalized_safe_action_types(
            safe_action_types if safe_action_types is not None else settings.AGENT_WORKFLOW_RECOVERY_SAFE_ACTION_TYPES
        )
        candidates = agent_workflow_action_crud.list_retryable_workflow_candidates(
            db,
            team_id=team_id,
            user_id=user_id,
            include_system_actions=True,
            limit=batch_size,
        )
        workflows = _group_by_workflow(candidates)
        stats: JSONDict = {
            "scanned_actions": len(candidates),
            "scanned_workflows": len(workflows),
            "eligible_workflows": 0,
            "retried_workflows": 0,
            "retried_actions": 0,
            "dry_run": effective_dry_run,
            "skipped": {
                "no_safe_action": 0,
                "waiting_user": 0,
                "multiple_teams": 0,
                "multiple_sessions": 0,
                "missing_session": 0,
                "missing_user": 0,
            },
            "policy_reasons": {},
            "failed": 0,
            "decisions": [],
        }
        for workflow_id, retryable_actions in workflows.items():
            workflow_team_ids = {action.team_id for action in retryable_actions}
            if len(workflow_team_ids) != 1:
                decision = self._invalid_workflow_decision(
                    workflow_id,
                    retryable_actions,
                    reason="multiple_teams",
                    safe_actions=safe_actions,
                )
                stats["decisions"].append(decision.__dict__)
                _increment_skipped(stats, decision.reason)
                _merge_policy_reasons(stats, decision.policy_reasons)
                continue
            workflow_team_id = next(iter(workflow_team_ids))
            all_actions = agent_workflow_action_crud.list_by_workflow(
                db,
                workflow_id,
                team_id=workflow_team_id,
                user_id=user_id,
                include_system_actions=True,
            )
            decision = self._decide_workflow_recovery(workflow_id, all_actions, safe_actions=safe_actions)
            stats["decisions"].append(decision.__dict__)
            _merge_policy_reasons(stats, decision.policy_reasons)
            if not decision.eligible:
                skipped = stats["skipped"]
                if isinstance(skipped, dict):
                    skipped[decision.reason] = int(skipped.get(decision.reason, 0)) + 1
                continue
            stats["eligible_workflows"] = int(stats["eligible_workflows"]) + 1
            if effective_dry_run:
                continue
            try:
                session_id = _single_int({action.session_id for action in all_actions if action.session_id is not None})
                safe_retryable_actions = _safe_retryable_actions(all_actions, safe_actions=safe_actions)
                workflow_user_id = _workflow_user_id(all_actions)
                session = agent_session_crud.get_by_id(
                    db,
                    session_id,
                    team_id=workflow_team_id,
                    user_id=workflow_user_id,
                )
                if session is None:
                    _increment_skipped(stats, "missing_session")
                    continue
                await self.runtime.retry_workflow(
                    db=db,
                    workflow_id=workflow_id,
                    actions=safe_retryable_actions,
                    session=session,
                    team_id=workflow_team_id,
                    user_id=workflow_user_id,
                    authorization="",
                    retry_source=workflow_action_ledger.SOURCE_BACKGROUND_RECOVERY,
                    reason="agent_workflow_recovery",
                )
                stats["retried_workflows"] = int(stats["retried_workflows"]) + 1
                stats["retried_actions"] = int(stats["retried_actions"]) + decision.safe_action_count
            except Exception:
                stats["failed"] = int(stats["failed"]) + 1
                logger.exception("Agent workflow recovery failed for workflow_id=%s", workflow_id)
        return stats

    def _invalid_workflow_decision(
        self,
        workflow_id: str,
        retryable_actions: list[AgentWorkflowAction],
        *,
        reason: str,
        safe_actions: set[str],
    ) -> WorkflowRecoveryDecision:
        policy_decisions = [
            evaluate_background_recovery_policy(action, safe_action_types=safe_actions) for action in retryable_actions
        ]
        return _decision(
            workflow_id,
            retryable_actions,
            retryable_actions,
            [],
            reason,
            policy_reasons=_policy_reason_counts(policy_decisions),
            retryable_action_policies=[policy.to_dict() for policy in policy_decisions],
        )

    def _decide_workflow_recovery(
        self,
        workflow_id: str,
        actions: list[AgentWorkflowAction],
        *,
        safe_actions: set[str],
    ) -> WorkflowRecoveryDecision:
        retryable_actions = [action for action in actions if _is_retryable(action)]
        policy_decisions = [
            evaluate_background_recovery_policy(action, safe_action_types=safe_actions) for action in retryable_actions
        ]
        policy_reasons = _policy_reason_counts(policy_decisions)
        safe_retryable_actions = [
            action
            for action, policy in zip(retryable_actions, policy_decisions, strict=False)
            if policy.allowed
        ]
        if any(action.execution_policy == action_workflow.EXECUTION_REQUIRES_CONFIRMATION for action in retryable_actions):
            return _decision(
                workflow_id,
                actions,
                retryable_actions,
                safe_retryable_actions,
                "waiting_user",
                policy_reasons=policy_reasons,
                retryable_action_policies=[policy.to_dict() for policy in policy_decisions],
            )
        if not safe_retryable_actions:
            return _decision(
                workflow_id,
                actions,
                retryable_actions,
                safe_retryable_actions,
                "no_safe_action",
                policy_reasons=policy_reasons,
                retryable_action_policies=[policy.to_dict() for policy in policy_decisions],
            )
        session_ids = {action.session_id for action in actions if action.session_id is not None}
        if len(session_ids) != 1:
            return _decision(
                workflow_id,
                actions,
                retryable_actions,
                safe_retryable_actions,
                "multiple_sessions",
                policy_reasons=policy_reasons,
                retryable_action_policies=[policy.to_dict() for policy in policy_decisions],
            )
        user_ids = {action.user_id for action in actions if action.user_id is not None}
        if len(user_ids) != 1:
            return _decision(
                workflow_id,
                actions,
                retryable_actions,
                safe_retryable_actions,
                "missing_user",
                policy_reasons=policy_reasons,
                retryable_action_policies=[policy.to_dict() for policy in policy_decisions],
            )
        return _decision(
            workflow_id,
            actions,
            retryable_actions,
            safe_retryable_actions,
            "eligible",
            eligible=True,
            policy_reasons=policy_reasons,
            retryable_action_policies=[policy.to_dict() for policy in policy_decisions],
        )


def _decision(
    workflow_id: str,
    actions: list[AgentWorkflowAction],
    retryable_actions: list[AgentWorkflowAction],
    safe_actions: list[AgentWorkflowAction],
    reason: str,
    *,
    eligible: bool = False,
    policy_reasons: dict[str, int] | None = None,
    retryable_action_policies: list[dict[str, object]] | None = None,
) -> WorkflowRecoveryDecision:
    return WorkflowRecoveryDecision(
        workflow_id=workflow_id,
        eligible=eligible,
        reason=reason,
        action_count=len(actions),
        retryable_action_count=len(retryable_actions),
        safe_action_count=len(safe_actions),
        policy_reasons=policy_reasons or {},
        retryable_action_policies=retryable_action_policies or [],
    )


def _group_by_workflow(actions: list[AgentWorkflowAction]) -> dict[str, list[AgentWorkflowAction]]:
    grouped: dict[str, list[AgentWorkflowAction]] = defaultdict(list)
    for action in actions:
        if action.workflow_id:
            grouped[action.workflow_id].append(action)
    return dict(grouped)


def _is_retryable(action: AgentWorkflowAction) -> bool:
    return action.status in {"FAILED", "BLOCKED"}


def _safe_retryable_actions(actions: list[AgentWorkflowAction], *, safe_actions: set[str]) -> list[AgentWorkflowAction]:
    return [
        action
        for action in actions
        if evaluate_background_recovery_policy(action, safe_action_types=safe_actions).allowed
    ]


def _policy_reason_counts(policy_decisions: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for policy in policy_decisions:
        reason = getattr(policy, "reason", None)
        if isinstance(reason, str) and reason != REASON_ALLOWED:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _single_int(values: set[int]) -> int:
    if len(values) != 1:
        raise ValueError("expected exactly one session id")
    return next(iter(values))


def _workflow_user_id(actions: list[AgentWorkflowAction]) -> int:
    return _single_int({action.user_id for action in actions if action.user_id is not None})


def _increment_skipped(stats: JSONDict, reason: str) -> None:
    skipped = stats.get("skipped")
    if isinstance(skipped, dict):
        skipped[reason] = int(skipped.get(reason, 0)) + 1


def _merge_policy_reasons(stats: JSONDict, policy_reasons: dict[str, int]) -> None:
    current = stats.get("policy_reasons")
    if not isinstance(current, dict):
        current = {}
        stats["policy_reasons"] = current
    for reason, count in policy_reasons.items():
        current[reason] = int(current.get(reason, 0)) + count


agent_workflow_recovery_service = AgentWorkflowRecoveryService()
