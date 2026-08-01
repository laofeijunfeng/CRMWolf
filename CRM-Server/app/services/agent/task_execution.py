"""Agent confirmed task execution."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import uuid
from typing import Optional

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
from app.services.agent.tools.base import AgentToolContext, AgentToolResult
from app.services.agent.types import AgentRuntimeEventSink, JSONDict
from app.utils.sse_encoder import SSEJsonEncoder

from app.services.agent import agent_copy, task_display
from app.services.agent.follow_up_fields import (
    _stage_customer_activity_after_create,
    _stage_lead_follow_up_after_create,
)
from app.services.agent.task_actions import _tool_name_for_action, _tool_payload_for_action
from app.services.agent.task_factory import _new_task_key


@dataclass(frozen=True)
class WaitingTaskExecutionResult:
    tool_result: object | None
    assistant_content: str
    next_task: object | None = None
    progress_events: list[JSONDict] = field(default_factory=list)


async def _execute_waiting_task(
    db: Session,
    task,
    session,
    team_id: int,
    user_id: int,
    authorization: str,
    event_sink: AgentRuntimeEventSink | None = None,
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
    progress_events: list[JSONDict] = []
    if action == "move_opportunity_stage" and tool_name:
        result = await _execute_opportunity_stage_move_plan(
            runtime,
            context,
            payload,
            task.task_key,
            progress_events=progress_events,
            event_sink=event_sink,
        )
    elif tool_name and tool_payload:
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
                        summary="登记本次回款",
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
                return WaitingTaskExecutionResult(result, "回款计划已创建。请确认是否登记本次回款？", next_task, progress_events)
            return WaitingTaskExecutionResult(result, "回款计划已创建。", progress_events=progress_events)
        if action == "create_payment_record":
            return WaitingTaskExecutionResult(result, "回款已登记，并已按系统现有流程提交审批。", progress_events=progress_events)
        if action == "create_lead":
            lead_id = result.data.get("id") if isinstance(result.data, dict) else None
            follow_up = payload.get("lead_follow_up") or {}
            if lead_id and isinstance(follow_up, dict) and follow_up.get("content"):
                assistant_content, next_task = await _stage_lead_follow_up_after_create(
                    db,
                    session,
                    task,
                    team_id=team_id,
                    user_id=user_id,
                    lead_id=lead_id,
                    follow_up=follow_up,
                )
                return WaitingTaskExecutionResult(result, assistant_content, next_task, progress_events)
            return WaitingTaskExecutionResult(result, "线索已创建。", progress_events=progress_events)
        if action == "create_customer":
            customer_id = result.data.get("id") if isinstance(result.data, dict) else None
            customer_name = result.data.get("account_name") if isinstance(result.data, dict) else None
            customer = {
                "id": customer_id,
                "account_name": customer_name or (payload.get("customer") or {}).get("account_name"),
            }
            activity = payload.get("customer_activity") or payload.get("customer_follow_up") or {}
            if customer_id and isinstance(activity, dict) and activity.get("content"):
                assistant_content, next_task = await _stage_customer_activity_after_create(
                    db,
                    session,
                    task,
                    team_id=team_id,
                    user_id=user_id,
                    customer=customer,
                    activity=activity,
                )
                return WaitingTaskExecutionResult(result, assistant_content, next_task, progress_events)
            return WaitingTaskExecutionResult(result, "客户已创建。", progress_events=progress_events)
        if action == "create_lead_follow_up":
            return WaitingTaskExecutionResult(result, "线索跟进记录已创建。", progress_events=progress_events)
        if action == "create_contact":
            return WaitingTaskExecutionResult(result, "联系人已创建。", progress_events=progress_events)
        if action == "create_invoice_title":
            return WaitingTaskExecutionResult(result, "发票抬头已创建。", progress_events=progress_events)
        if action == "create_deployment_info":
            return WaitingTaskExecutionResult(result, "部署信息已创建。", progress_events=progress_events)
        if action == "create_customer_member":
            return WaitingTaskExecutionResult(result, "客户成员已添加。", progress_events=progress_events)
        if action == "create_opportunity":
            return WaitingTaskExecutionResult(result, "商机已创建，并已按系统现有流程提交审批。", progress_events=progress_events)
        if action == "move_opportunity_stage":
            stage_name = None
            if isinstance(result.data, dict):
                current_stage = result.data.get("current_stage_snapshot") or {}
                stage_name = current_stage.get("stage_name")
            return WaitingTaskExecutionResult(
                result,
                f"商机阶段已推进{f'到「{stage_name}」' if stage_name else ''}。",
                progress_events=progress_events,
            )
        if action == "create_customer_activity" and isinstance(payload.get("_next_task"), dict):
            next_action = payload["_next_task"]
            next_payload = next_action.get("payload") or {}
            next_content = next_action.get("content")
            next_summary = (
                next_content
                if isinstance(next_content, str) and next_content.strip() and "_" not in next_content
                else task_display.readable_action_label(next_action.get("action")) or "等待确认业务操作"
            )
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
                    summary=next_summary,
                    input_json=next_payload,
                    state_json={
                        "action": next_action.get("action"),
                        "payload": next_payload,
                        "customer": next_action.get("customer") or customer,
                        "opportunities": next_action.get("opportunities") or [],
                        "hitl": AgentHITLPolicy(
                            required_for_tools=[_tool_name_for_action(next_action.get("action"))]
                            if _tool_name_for_action(next_action.get("action"))
                            else [],
                            confirmation_summary=next_action.get("content") or "等待确认执行下一步动作",
                        ).model_dump(exclude_none=True),
                    },
                ),
            )
            return WaitingTaskExecutionResult(
                result,
                agent_copy.customer_activity_created_with_next(next_action.get("content")),
                next_task,
                progress_events,
            )
        if action == "create_customer_activity":
            return WaitingTaskExecutionResult(result, agent_copy.customer_activity_created(), progress_events=progress_events)
        return WaitingTaskExecutionResult(result, agent_copy.generic_completed(), progress_events=progress_events)

    error_message = result.error_message if result else f"暂不支持的执行动作：{action}"
    agent_task_crud.update(
        db,
        task,
        AgentTaskUpdate(status=AgentTaskStatus.FAILED, error_message=error_message),
    )
    return WaitingTaskExecutionResult(result, f"执行失败：{error_message}", progress_events=progress_events)


async def _execute_opportunity_stage_move_plan(
    runtime: AgentToolRuntime,
    context: AgentToolContext,
    payload: dict,
    task_key: str,
    progress_events: list[JSONDict],
    event_sink: AgentRuntimeEventSink | None,
) -> AgentToolResult:
    raw_steps = payload.get("stage_move_steps")
    steps = [step for step in raw_steps if isinstance(step, dict)] if isinstance(raw_steps, list) else []
    if not steps:
        stage_template_id = payload.get("stage_template_id")
        steps = [{"stage_template_id": stage_template_id, "stage_name": payload.get("target_stage_name")}]

    executed_steps = []
    last_result: AgentToolResult | None = None
    for index, step in enumerate(steps, start=1):
        stage_template_id = step.get("stage_template_id")
        if not stage_template_id:
            return AgentToolResult(
                tool_name="move_opportunity_stage",
                success=False,
                error_message="缺少商机阶段模板 ID",
            )
        tool_payload = {
            "opportunity_id": payload["opportunity_id"],
            "stage_template_id": int(stage_template_id),
            "idempotency_suffix": f"{task_key}:stage:{index}",
        }
        stage_name = step.get("stage_name")
        progress_label = f"推进到「{stage_name.strip()}」" if isinstance(stage_name, str) and stage_name.strip() else "推进商机阶段"
        await _append_progress_event(
            progress_events,
            event_sink,
            f"opportunity_stage_move_{index}",
            "started",
            progress_label,
        )
        last_result = await runtime.execute(
            "move_opportunity_stage",
            context,
            tool_payload,
            policy=AgentToolExecutionPolicy(
                hitl_decision="approve",
                allowed_tool_names=["move_opportunity_stage"],
                allowed_customer_ids=[int(payload["customer_id"])] if payload.get("customer_id") else [],
            ),
        )
        if not last_result.success:
            await _append_progress_event(
                progress_events,
                event_sink,
                f"opportunity_stage_move_{index}",
                "completed",
                f"{progress_label}失败",
            )
            return last_result
        await _append_progress_event(
            progress_events,
            event_sink,
            f"opportunity_stage_move_{index}",
            "completed",
            progress_label,
        )
        executed_steps.append({
            "stage_template_id": int(stage_template_id),
            "stage_name": step.get("stage_name"),
            "tool_call_id": last_result.tool_call_id,
        })

    data = last_result.data if last_result else {}
    if not isinstance(data, dict):
        data = {"result": data}
    return AgentToolResult(
        tool_name="move_opportunity_stage",
        success=True,
        data={
            **data,
            "stage_move_steps": executed_steps,
        },
        status_code=last_result.status_code if last_result else None,
        tool_call_id=last_result.tool_call_id if last_result else None,
        idempotent_replay=bool(last_result.idempotent_replay) if last_result else False,
    )


async def _append_progress_event(
    progress_events: list[JSONDict],
    event_sink: AgentRuntimeEventSink | None,
    step: str,
    status: str,
    content: str,
) -> None:
    event: JSONDict = {
        "event": "agent_step",
        "step": step,
        "status": status,
        "content": content,
    }
    progress_events.append(event)
    if event_sink:
        await event_sink(event)
