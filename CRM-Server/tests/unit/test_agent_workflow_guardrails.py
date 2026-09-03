"""Native Workflow authorization behavior through the tool registry seam."""

from __future__ import annotations

import pytest

from app.services.agent.guardrails import AgentToolExecutionPolicy, AgentToolGuardrailError
from app.services.agent.tool_registry import AgentToolRegistry
from app.services.agent.tools.base import AgentToolContext, AgentToolResult

CUSTOMER_ID = "cus_shanghai_001"


class CapturingCustomerActivityService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_customer_activity(self, context: AgentToolContext, **payload: object) -> AgentToolResult:
        self.calls.append({"context": context, "payload": payload})
        return AgentToolResult(
            tool_name="create_customer_activity",
            success=True,
            data={"id": "actv_001"},
        )


def _context(*, confirmed: bool = True) -> AgentToolContext:
    return AgentToolContext(
        db=object(),  # type: ignore[arg-type]
        team_id=1,
        user_id=2,
        session_id=556,
        authorization="Bearer test-token",
        workflow_id="wf_native_confirmation_001",
        action_id="act_create_customer_activity_001",
        hitl_decision="approve" if confirmed else None,
        confirmed_by_user=confirmed,
        allowed_tool_names=["create_customer_activity"],
        allowed_customer_ids=[CUSTOMER_ID],
    )


def _policy() -> AgentToolExecutionPolicy:
    return AgentToolExecutionPolicy(
        hitl_decision="approve",
        workflow_id="wf_native_confirmation_001",
        action_id="act_create_customer_activity_001",
        authorization_source="workflow_structured_confirmation",
        allowed_tool_names=["create_customer_activity"],
        allowed_customer_ids=[CUSTOMER_ID],
    )


def _payload(*, customer_id: str = CUSTOMER_ID) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "activity_kind": "PHONE_FOLLOW_UP",
        "source_content": "确认技术评估结论",
        "effectiveness_score": 80,
        "effectiveness_is_valid": True,
        "effectiveness_reason": "已确认技术评估结论",
    }


async def test_registry_allows_confirmed_native_workflow_without_legacy_task_projection() -> None:
    service = CapturingCustomerActivityService()
    registry = AgentToolRegistry(tool_service=service)  # type: ignore[arg-type]

    result = await registry.execute(
        "create_customer_activity",
        _context(),
        _payload(),
        policy=_policy(),
    )

    assert result.success is True
    assert len(service.calls) == 1
    assert service.calls[0]["payload"]["customer_id"] == CUSTOMER_ID


async def test_registry_blocks_unconfirmed_native_workflow_write() -> None:
    service = CapturingCustomerActivityService()
    registry = AgentToolRegistry(tool_service=service)  # type: ignore[arg-type]

    with pytest.raises(AgentToolGuardrailError, match="HITL approve"):
        await registry.execute(
            "create_customer_activity",
            _context(confirmed=False),
            _payload(),
            policy=AgentToolExecutionPolicy(
                workflow_id="wf_native_confirmation_001",
                action_id="act_create_customer_activity_001",
                allowed_tool_names=["create_customer_activity"],
                allowed_customer_ids=[CUSTOMER_ID],
            ),
        )

    assert service.calls == []


async def test_registry_blocks_native_workflow_tool_outside_confirmed_scope() -> None:
    service = CapturingCustomerActivityService()
    registry = AgentToolRegistry(tool_service=service)  # type: ignore[arg-type]
    context = _context()
    context.allowed_tool_names = ["create_lead"]

    with pytest.raises(AgentToolGuardrailError, match="不允许执行 tool"):
        await registry.execute(
            "create_customer_activity",
            context,
            _payload(),
            policy=AgentToolExecutionPolicy(
                hitl_decision="approve",
                workflow_id="wf_native_confirmation_001",
                action_id="act_create_customer_activity_001",
                allowed_tool_names=["create_lead"],
                allowed_customer_ids=[CUSTOMER_ID],
            ),
        )

    assert service.calls == []


async def test_registry_blocks_native_workflow_customer_outside_confirmed_scope() -> None:
    service = CapturingCustomerActivityService()
    registry = AgentToolRegistry(tool_service=service)  # type: ignore[arg-type]

    with pytest.raises(AgentToolGuardrailError, match="客户 ID 不在当前确认上下文内"):
        await registry.execute(
            "create_customer_activity",
            _context(),
            _payload(customer_id="cus_beijing_002"),
            policy=_policy(),
        )

    assert service.calls == []
