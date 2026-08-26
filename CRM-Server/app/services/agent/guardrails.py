"""Guardrails for CRM AI Agent tool execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.tools.base import AgentToolContext


class AgentToolGuardrailError(Exception):
    """Raised when a tool call violates Agent execution policy."""


@dataclass(frozen=True)
class AgentToolExecutionPolicy:
    """Runtime policy attached to a single tool execution."""

    hitl_decision: str | None = None
    execution_policy: str | None = None
    workflow_id: str | None = None
    action_id: str | None = None
    authorization_source: str | None = None
    auto_execute_authorized: bool = False
    allowed_tool_names: list[str] = field(default_factory=list)
    allowed_customer_ids: list[str] = field(default_factory=list)


class AgentToolGuardrails:
    """Policy checks that sit between LangGraph and CRM API tools."""

    APPROVED_DECISION = "approve"
    AUTO_EXECUTE_POLICY = "auto_execute"
    AUTO_EXECUTE_SOURCE = "semantic_auto_execute_low_risk"

    def validate_before_execute(
        self,
        *,
        tool_name: str,
        is_write: bool,
        requires_confirmation: bool,
        context: AgentToolContext,
        payload: dict[str, object],
        policy: AgentToolExecutionPolicy | None = None,
        user_reply_confirms: bool = False,
    ) -> None:
        policy = policy or AgentToolExecutionPolicy()
        allowed_tool_names = policy.allowed_tool_names or context.allowed_tool_names or []
        if allowed_tool_names and tool_name not in allowed_tool_names:
            raise AgentToolGuardrailError(f"当前任务不允许执行 tool: {tool_name}")

        if (
            (is_write or requires_confirmation)
            and not user_reply_confirms
            and not (
                self._is_hitl_approved(policy, context)
                or self._is_auto_execute_authorized(policy, context)
            )
        ):
            raise AgentToolGuardrailError("写入类 tool 必须经过 HITL approve 确认后才能执行。")

        allowed_customer_ids = policy.allowed_customer_ids or context.allowed_customer_ids or []
        customer_id = payload.get("customer_id")
        if customer_id is None and isinstance(payload.get("deployment_info"), dict):
            customer_id = payload["deployment_info"].get("customer_id")
        if customer_id is None and isinstance(payload.get("opportunity"), dict):
            customer_id = payload["opportunity"].get("customer_id")
        if customer_id is not None and allowed_customer_ids and str(customer_id) not in allowed_customer_ids:
            raise AgentToolGuardrailError("tool payload 中的客户 ID 不在当前确认上下文内。")

    def _is_hitl_approved(
        self,
        policy: AgentToolExecutionPolicy,
        context: AgentToolContext,
    ) -> bool:
        decision = policy.hitl_decision or context.hitl_decision
        workflow_id = policy.workflow_id or context.workflow_id
        action_id = policy.action_id or context.action_id
        allowed_tool_names = policy.allowed_tool_names or context.allowed_tool_names or []
        identity_matches = (
            (policy.workflow_id is None or context.workflow_id is None or policy.workflow_id == context.workflow_id)
            and (policy.action_id is None or context.action_id is None or policy.action_id == context.action_id)
        )
        return (
            decision == self.APPROVED_DECISION
            and context.confirmed_by_user
            and identity_matches
            and isinstance(workflow_id, str)
            and workflow_id.startswith("wf_")
            and isinstance(action_id, str)
            and action_id.startswith("act_")
            and bool(allowed_tool_names)
        )

    def _is_auto_execute_authorized(
        self,
        policy: AgentToolExecutionPolicy,
        context: AgentToolContext,
    ) -> bool:
        execution_policy = policy.execution_policy or context.execution_policy
        authorization_source = policy.authorization_source or context.authorization_source
        action_id = policy.action_id or context.action_id
        workflow_id = policy.workflow_id or context.workflow_id
        return (
            execution_policy == self.AUTO_EXECUTE_POLICY
            and authorization_source == self.AUTO_EXECUTE_SOURCE
            and bool(policy.auto_execute_authorized or context.auto_execute_authorized)
            and isinstance(action_id, str)
            and action_id.startswith("act_")
            and isinstance(workflow_id, str)
            and workflow_id.startswith("wf_")
        )


agent_tool_guardrails = AgentToolGuardrails()
