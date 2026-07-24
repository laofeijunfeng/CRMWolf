"""Guardrails for CRM AI Agent tool execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.agent.tools.base import AgentToolContext


class AgentToolGuardrailError(Exception):
    """Raised when a tool call violates Agent execution policy."""


@dataclass(frozen=True)
class AgentToolExecutionPolicy:
    """Runtime policy attached to a single tool execution."""

    hitl_decision: Optional[str] = None
    allowed_tool_names: List[str] = field(default_factory=list)
    allowed_customer_ids: List[int] = field(default_factory=list)


class AgentToolGuardrails:
    """Policy checks that sit between LangGraph and CRM API tools."""

    APPROVED_DECISION = "approve"

    def validate_before_execute(
        self,
        *,
        tool_name: str,
        is_write: bool,
        requires_confirmation: bool,
        context: AgentToolContext,
        payload: Dict[str, Any],
        policy: Optional[AgentToolExecutionPolicy] = None,
    ) -> None:
        policy = policy or AgentToolExecutionPolicy()
        allowed_tool_names = policy.allowed_tool_names or context.allowed_tool_names or []
        if allowed_tool_names and tool_name not in allowed_tool_names:
            raise AgentToolGuardrailError(f"当前任务不允许执行 tool：{tool_name}")

        if is_write or requires_confirmation:
            decision = policy.hitl_decision or context.hitl_decision
            if decision != self.APPROVED_DECISION or not context.confirmed_by_user or not context.task_id:
                raise AgentToolGuardrailError("写入类 tool 必须经过 HITL approve 确认后才能执行。")

        allowed_customer_ids = policy.allowed_customer_ids or context.allowed_customer_ids or []
        customer_id = payload.get("customer_id")
        if customer_id is None and isinstance(payload.get("deployment_info"), dict):
            customer_id = payload["deployment_info"].get("customer_id")
        if customer_id is None and isinstance(payload.get("opportunity"), dict):
            customer_id = payload["opportunity"].get("customer_id")
        if customer_id is not None and allowed_customer_ids and int(customer_id) not in allowed_customer_ids:
            raise AgentToolGuardrailError("tool payload 中的客户 ID 不在当前确认上下文内。")


agent_tool_guardrails = AgentToolGuardrails()
