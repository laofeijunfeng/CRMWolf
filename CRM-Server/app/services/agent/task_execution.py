"""Agent confirmed task execution."""
from __future__ import annotations

from copy import deepcopy
import json
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud.agent import agent_session_crud, agent_task_crud
from app.crud.procurement import procurement_method_crud
from app.models.agent import AgentTaskStatus
from app.models.customer import Customer
from app.schemas.agent import (
    AgentCreateSessionRequest,
    AgentSessionCreate,
    AgentSessionUpdate,
    AgentTaskCreate,
    AgentTaskUpdate,
)
from app.services.agent.guardrails import AgentToolExecutionPolicy
from app.services.agent.quality import AgentFollowUpQualityEvaluatorError, agent_follow_up_quality_evaluator
from app.services.agent.runtime import AgentToolRuntime
from app.services.agent.schemas import (
    AgentHITLPolicy,
    AgentMemorySnapshot,
    AgentPendingInterruptionDecision,
    AgentSemanticParseResult,
)
from app.services.agent.semantic import AgentSemanticParserError, agent_semantic_parser
from app.services.agent.temporal import agent_temporal_resolver
from app.services.agent.tools.api_client import CRMAPIClientError
from app.services.agent.tool_registry import AgentToolRegistry
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext
from app.utils.sse_encoder import SSEJsonEncoder

from app.services.agent import agent_copy
from app.services.agent.follow_up_fields import (
    _stage_customer_activity_after_create,
    _stage_lead_follow_up_after_create,
)
from app.services.agent.session_state import _remember_pending_task
from app.services.agent.task_actions import _tool_name_for_action, _tool_payload_for_action
from app.services.agent.task_factory import _new_task_key


async def _execute_waiting_task(
    db: Session,
    task,
    session,
    team_id: int,
    user_id: int,
    authorization: str,
):
    state = task.state_json or {}
    action = state.get("action")
    payload = state.get("payload") or {}
    customer = state.get("customer") or {}
    tool_name = _tool_name_for_action(action)
    tool_payload = _tool_payload_for_action(action, payload, customer, task.task_key)
    context = AgentToolContext(
        db=db,
        team_id=team_id,
        user_id=user_id,
        session_id=session.id,
        task_id=task.id,
        authorization=authorization,
        hitl_decision="approve",
        confirmed_by_user=True,
        allowed_tool_names=[tool_name] if tool_name else [],
        allowed_customer_ids=[customer["id"]] if customer.get("id") else [],
    )
    registry = AgentToolRegistry(CRMAgentToolService())
    runtime = AgentToolRuntime(registry)

    agent_task_crud.update(db, task, AgentTaskUpdate(status=AgentTaskStatus.RUNNING))
    result = None
    if tool_name and tool_payload:
        result = await runtime.execute(
            tool_name,
            context,
            tool_payload,
            policy=AgentToolExecutionPolicy(
                hitl_decision="approve",
                allowed_tool_names=[tool_name],
                allowed_customer_ids=[customer["id"]] if customer.get("id") else [],
            ),
        )

    if result and result.success:
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(status=AgentTaskStatus.COMPLETED, result_json=result.data),
        )
        if action == "create_payment_plan":
            created_items = result.data.get("items") if isinstance(result.data, dict) else result.data
            created_plan = created_items[0] if isinstance(created_items, list) and created_items else result.data
            pending_record = payload.get("pending_payment_record") or {}
            if isinstance(created_plan, dict) and created_plan.get("id") and pending_record:
                next_payload = {
                    "payment_plan_id": created_plan.get("id"),
                    **pending_record,
                }
                next_task = agent_task_crud.create(
                    db,
                    AgentTaskCreate(
                        task_key=_new_task_key(),
                        team_id=team_id,
                        user_id=user_id,
                        session_id=session.id,
                        intent="PAYMENT_RECORD",
                        status=AgentTaskStatus.WAITING_USER,
                        target_type="customer",
                        target_id=customer.get("id"),
                        summary="等待确认执行：create_payment_record",
                        input_json=next_payload,
                        state_json={
                            "action": "create_payment_record",
                            "payload": next_payload,
                            "customer": customer,
                            "hitl": AgentHITLPolicy(
                                required_for_tools=["create_payment_record"],
                                confirmation_summary="登记本次回款",
                            ).model_dump(exclude_none=True),
                        },
                    ),
                )
                _remember_pending_task(db, session, next_task)
                return result, "回款计划已创建。请确认是否登记本次回款？"
            return result, "回款计划已创建。"
        if action == "create_payment_record":
            return result, "回款已登记，并已按系统现有流程提交审批。"
        if action == "create_lead":
            lead_id = result.data.get("id") if isinstance(result.data, dict) else None
            follow_up = payload.get("lead_follow_up") or {}
            if lead_id and isinstance(follow_up, dict) and follow_up.get("content"):
                assistant_content = await _stage_lead_follow_up_after_create(
                    db,
                    session,
                    task,
                    team_id=team_id,
                    user_id=user_id,
                    lead_id=lead_id,
                    follow_up=follow_up,
                )
                return result, assistant_content
            return result, "线索已创建。"
        if action == "create_customer":
            customer_id = result.data.get("id") if isinstance(result.data, dict) else None
            customer_name = result.data.get("account_name") if isinstance(result.data, dict) else None
            customer = {
                "id": customer_id,
                "account_name": customer_name or (payload.get("customer") or {}).get("account_name"),
            }
            activity = payload.get("customer_activity") or payload.get("customer_follow_up") or {}
            if customer_id and isinstance(activity, dict) and activity.get("content"):
                assistant_content = await _stage_customer_activity_after_create(
                    db,
                    session,
                    task,
                    team_id=team_id,
                    user_id=user_id,
                    customer=customer,
                    activity=activity,
                )
                return result, assistant_content
            return result, "客户已创建。"
        if action == "create_lead_follow_up":
            return result, "线索跟进记录已创建。"
        if action == "create_contact":
            return result, "联系人已创建。"
        if action == "create_invoice_title":
            return result, "发票抬头已创建。"
        if action == "create_deployment_info":
            return result, "部署信息已创建。"
        if action == "create_customer_member":
            return result, "客户成员已添加。"
        if action == "create_opportunity":
            return result, "商机已创建，并已按系统现有流程提交审批。"
        if action == "move_opportunity_stage":
            stage_name = None
            if isinstance(result.data, dict):
                current_stage = result.data.get("current_stage_snapshot") or {}
                stage_name = current_stage.get("stage_name")
            return result, f"商机阶段已推进{f'到「{stage_name}」' if stage_name else ''}。"
        if action == "create_customer_activity" and isinstance(payload.get("_next_task"), dict):
            next_action = payload["_next_task"]
            next_payload = next_action.get("payload") or {}
            next_task = agent_task_crud.create(
                db,
                AgentTaskCreate(
                    task_key=_new_task_key(),
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    intent="CUSTOMER_ACTIVITY",
                    status=AgentTaskStatus.WAITING_USER,
                    target_type="customer",
                    target_id=next_payload.get("customer_id") or customer.get("id"),
                    summary=f"等待确认执行：{next_action.get('action')}",
                    input_json=next_payload,
                    state_json={
                        "action": next_action.get("action"),
                        "payload": next_payload,
                        "customer": next_action.get("customer") or customer,
                        "hitl": AgentHITLPolicy(
                            required_for_tools=[_tool_name_for_action(next_action.get("action"))]
                            if _tool_name_for_action(next_action.get("action"))
                            else [],
                            confirmation_summary=next_action.get("content") or "等待确认执行下一步动作",
                        ).model_dump(exclude_none=True),
                    },
                ),
            )
            _remember_pending_task(db, session, next_task)
            return result, agent_copy.customer_activity_created_with_next(next_action.get("content"))
        if action == "create_customer_activity":
            return result, agent_copy.customer_activity_created()
        return result, agent_copy.generic_completed()

    error_message = result.error_message if result else f"暂不支持的执行动作：{action}"
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.FAILED, error_message=error_message),
    )
    return result, f"执行失败：{error_message}"
