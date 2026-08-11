"""Policy layer for Agent workflow background recovery.

Background recovery is intentionally stricter than manual retry. Manual/API
retry carries an authenticated user request; background recovery does not. This
module keeps that distinction explicit so a scheduler cannot silently become a
second business mutation path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.models.agent import AgentWorkflowAction
from app.services.agent import action_workflow

RECOVERY_MODE_DRY_RUN_ONLY = "dry_run_only"
RECOVERY_MODE_ROOT_RUNTIME_RETRY = "root_runtime_retry"

REASON_ALLOWED = "allowed"
REASON_NOT_RETRYABLE = "not_retryable"
REASON_ACTION_TYPE_NOT_ALLOWLISTED = "action_type_not_allowlisted"
REASON_SCOPE_NOT_DERIVED_AUTOMATION = "scope_not_derived_automation"
REASON_POLICY_REQUIRES_CONFIRMATION = "policy_requires_confirmation"
REASON_POLICY_NOT_AUTO_EXECUTE = "policy_not_auto_execute"
REASON_USER_AUTHORIZATION_REQUIRED = "user_authorization_required"
REASON_BACKGROUND_RECOVERY_NOT_ALLOWED = "background_recovery_not_allowed"


@dataclass(frozen=True)
class WorkflowActionRecoveryPolicyDecision:
    action_id: str
    action_type: str
    allowed: bool
    reason: str
    execution_mode: str
    requires_user_authorization: bool

    def to_dict(self) -> dict[str, object]:
        capability = action_workflow.action_capability(self.action_type)
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "allowed": self.allowed,
            "reason": self.reason,
            "execution_mode": self.execution_mode,
            "requires_user_authorization": self.requires_user_authorization,
            "allows_background_recovery": capability.allows_background_recovery,
            "parallel_safe": capability.parallel_safe,
            "requires_idempotency_key": capability.requires_idempotency_key,
            "capability_flags": sorted(capability.flags),
        }


def evaluate_background_recovery_policy(
    action: AgentWorkflowAction,
    *,
    safe_action_types: Iterable[str],
) -> WorkflowActionRecoveryPolicyDecision:
    """Classify whether a failed ledger action may be retried by a scheduler."""

    safe_actions = normalized_safe_action_types(safe_action_types)
    requires_user_authorization = action_workflow.action_requires_user_authorization(action.action_type)
    if action.status not in {"FAILED", "BLOCKED"}:
        return _decision(action, REASON_NOT_RETRYABLE, requires_user_authorization=requires_user_authorization)
    if action.execution_policy == action_workflow.EXECUTION_REQUIRES_CONFIRMATION:
        return _decision(
            action,
            REASON_POLICY_REQUIRES_CONFIRMATION,
            requires_user_authorization=requires_user_authorization,
        )
    if action.scope != action_workflow.SCOPE_DERIVED_AUTOMATION:
        return _decision(
            action,
            REASON_SCOPE_NOT_DERIVED_AUTOMATION,
            requires_user_authorization=requires_user_authorization,
        )
    if action.execution_policy != action_workflow.EXECUTION_AUTO_EXECUTE:
        return _decision(
            action,
            REASON_POLICY_NOT_AUTO_EXECUTE,
            requires_user_authorization=requires_user_authorization,
        )
    if requires_user_authorization:
        return _decision(
            action,
            REASON_USER_AUTHORIZATION_REQUIRED,
            requires_user_authorization=True,
        )
    if not action_workflow.action_allows_background_recovery(action.action_type):
        return _decision(
            action,
            REASON_BACKGROUND_RECOVERY_NOT_ALLOWED,
            requires_user_authorization=False,
        )
    if action.action_type not in safe_actions:
        return _decision(
            action,
            REASON_ACTION_TYPE_NOT_ALLOWLISTED,
            requires_user_authorization=requires_user_authorization,
        )
    return WorkflowActionRecoveryPolicyDecision(
        action_id=action.action_id,
        action_type=action.action_type,
        allowed=True,
        reason=REASON_ALLOWED,
        execution_mode=RECOVERY_MODE_ROOT_RUNTIME_RETRY,
        requires_user_authorization=False,
    )


def normalized_safe_action_types(value: Iterable[str] | str | None) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    return {item.strip() for item in value if isinstance(item, str) and item.strip()}


def _decision(
    action: AgentWorkflowAction,
    reason: str,
    *,
    requires_user_authorization: bool,
) -> WorkflowActionRecoveryPolicyDecision:
    return WorkflowActionRecoveryPolicyDecision(
        action_id=action.action_id,
        action_type=action.action_type,
        allowed=False,
        reason=reason,
        execution_mode=RECOVERY_MODE_DRY_RUN_ONLY,
        requires_user_authorization=requires_user_authorization,
    )
