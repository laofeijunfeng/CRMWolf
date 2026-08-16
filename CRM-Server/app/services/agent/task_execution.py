"""Agent confirmed task execution."""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.crud.agent import agent_task_crud
from app.models.agent import AgentTaskStatus
from app.schemas.agent import (
    AgentTaskUpdate,
)
from app.services.agent import action_workflow, agent_copy, task_display, workflow_action_ledger
from app.services.agent.follow_up_fields import (
    _stage_customer_activity_after_create,
    _stage_lead_follow_up_after_create,
)
from app.services.agent.guardrails import AgentToolExecutionPolicy
from app.services.agent.next_waiting_task_projection import (
    NextWaitingTaskProjectionRequest,
    NextWaitingTaskSpec,
    next_waiting_task_projector,
)
from app.services.agent.runtime import AgentToolRuntime
from app.services.agent.task_actions import _tool_name_for_action, _tool_payload_for_action
from app.services.agent.task_factory import _task_target_id
from app.services.agent.tool_registry import AgentToolRegistry
from app.services.agent.tools import CRMAgentToolService
from app.services.agent.tools.base import AgentToolContext, AgentToolResult
from app.services.agent.types import AgentRuntimeEventSink, JSONDict, coerce_json_dict


@dataclass(frozen=True)
class WaitingTaskExecutionResult:
    tool_result: object | None
    assistant_content: str
    next_task: object | None = None
    progress_events: list[JSONDict] = field(default_factory=list)


@dataclass(frozen=True)
class ActionExecutionEnvelope:
    """Action-owned execution input.

    ``AgentTask`` is a confirmation/UI projection. The executable command is
    the action envelope: action id/type, workflow policy, payload and target
    customer context.
    """

    action_id: str
    action_type: str
    workflow: JSONDict = field(default_factory=dict)
    payload: JSONDict = field(default_factory=dict)
    customer: JSONDict = field(default_factory=dict)
    task_id: int | None = None
    task_key: str | None = None
    session_id: int | None = None
    target_type: str | None = None
    target_id: int | None = None


@dataclass(frozen=True)
class ActionToolExecutionResult:
    tool_result: AgentToolResult | None
    progress_events: list[JSONDict] = field(default_factory=list)


def execution_envelope_from_task(task: object) -> ActionExecutionEnvelope:
    state = coerce_json_dict(getattr(task, "state_json", None))
    workflow = action_workflow.workflow_from_task_state(state)
    action = _action_type_from_state(state, workflow)
    task_id = _optional_int(getattr(task, "id", None))
    return ActionExecutionEnvelope(
        action_id=_action_id_from_workflow_or_task(workflow=workflow, task_id=task_id),
        action_type=action,
        workflow=workflow,
        payload=_payload_from_task_state(task=task, state=state),
        customer=coerce_json_dict(state.get("customer")),
        task_id=task_id,
        task_key=_optional_str(getattr(task, "task_key", None)) or f"task_{task_id or 'unknown'}",
        session_id=_optional_int(getattr(task, "session_id", None)),
        target_type=_optional_str(getattr(task, "target_type", None)),
        target_id=_optional_int(getattr(task, "target_id", None)),
    )


def execution_envelope_from_plan_node(node: object) -> ActionExecutionEnvelope:
    workflow = action_workflow.workflow_from_mapping(getattr(node, "workflow", None))
    payload = coerce_json_dict(getattr(node, "payload", None))
    task = getattr(node, "task", None)
    task_envelope = execution_envelope_from_task(task) if task is not None else None
    customer = coerce_json_dict(payload.get("customer"))
    if not customer and task_envelope is not None:
        customer = task_envelope.customer
    target_type = _optional_str(getattr(node, "target_type", None))
    target_id = _optional_int(getattr(node, "target_id", None))
    action_type = _optional_str(getattr(node, "action_type", None))
    task_id = _optional_int(getattr(node, "task_id", None))
    return ActionExecutionEnvelope(
        action_id=_optional_str(getattr(node, "action_id", None))
        or _action_id_from_workflow_or_task(workflow=workflow, task_id=task_id),
        action_type=action_type or str(workflow.get("action_type") or "unknown"),
        workflow=workflow,
        payload=payload or (task_envelope.payload if task_envelope is not None else {}),
        customer=customer,
        task_id=task_id,
        task_key=(task_envelope.task_key if task_envelope is not None else None) or f"action_{_optional_str(getattr(node, 'action_id', None)) or 'unknown'}",
        session_id=task_envelope.session_id if task_envelope is not None else None,
        target_type=target_type,
        target_id=target_id,
    )


def can_direct_execute_action_envelope(envelope: ActionExecutionEnvelope) -> bool:
    """Return whether an action envelope is complete enough to run without task projection."""

    if not action_workflow.workflow_from_mapping(envelope.workflow):
        return False
    payload = envelope.payload
    action_type = envelope.action_type
    if action_type == "create_customer_activity":
        if isinstance(payload.get("_next_task"), dict):
            return False
        customer_id = payload.get("customer_id") or envelope.customer.get("id")
        return bool(customer_id and (payload.get("source_content") or payload.get("content")))
    if action_type == "transition_follow_up_task":
        return bool(payload.get("task_id") and payload.get("transition_action"))
    return False


def action_execution_blocking_reason(envelope: ActionExecutionEnvelope) -> str | None:
    """Validate capability requirements before a CRM mutation reaches tools."""

    capability = action_workflow.action_capability(envelope.action_type)
    if not (
        capability.is_write
        or capability.requires_idempotency_key
        or capability.required_payload_fields
    ):
        return None
    try:
        tool_payload = _tool_payload_for_action(
            envelope.action_type,
            envelope.payload,
            envelope.customer,
            envelope.task_key or envelope.action_id,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return f"invalid_action_payload:{exc}"
    if capability.requires_idempotency_key and not _payload_has_idempotency_key(tool_payload):
        return "missing_idempotency_key"
    validation_error = _tool_payload_validation_error(capability.tool_name, tool_payload)
    if validation_error:
        return validation_error
    missing_fields = [
        field
        for field in capability.required_payload_fields
        if not _payload_field_present(envelope.payload, field)
    ]
    if missing_fields:
        return f"missing_required_payload_fields:{','.join(sorted(missing_fields))}"
    return None


def _tool_execution_policy(
    *,
    tool_name: str,
    context: AgentToolContext,
    allowed_customer_ids: list[str],
) -> AgentToolExecutionPolicy:
    is_auto_execute = context.execution_policy == action_workflow.EXECUTION_AUTO_EXECUTE
    return AgentToolExecutionPolicy(
        hitl_decision=None if is_auto_execute else "approve",
        execution_policy=context.execution_policy,
        workflow_id=context.workflow_id,
        action_id=context.action_id,
        authorization_source=context.authorization_source,
        auto_execute_authorized=context.auto_execute_authorized,
        allowed_tool_names=[tool_name],
        allowed_customer_ids=allowed_customer_ids,
    )


async def execute_action_envelope(
    db: Session,
    envelope: ActionExecutionEnvelope,
    *,
    session: object,
    team_id: int,
    user_id: int,
    authorization: str,
    event_sink: AgentRuntimeEventSink | None = None,
) -> ActionToolExecutionResult:
    action = envelope.action_type
    tool_name = _tool_name_for_action(action)
    workflow = action_workflow.workflow_from_mapping(envelope.workflow)
    is_auto_execute = action_workflow.is_auto_execute_workflow(workflow)
    workflow_id = _optional_str(workflow.get("workflow_id"))
    action_id = _optional_str(workflow.get("action_id")) or envelope.action_id
    authorization_source = "semantic_auto_execute_low_risk" if is_auto_execute else None
    blocking_reason = action_execution_blocking_reason(envelope)
    if blocking_reason:
        return ActionToolExecutionResult(
            AgentToolResult(
                tool_name=tool_name or action or "unknown",
                success=False,
                error_message=blocking_reason,
                status_code=status.HTTP_409_CONFLICT,
            )
        )
    tool_payload = _tool_payload_for_action(action, envelope.payload, envelope.customer, envelope.task_key or envelope.action_id)
    context = AgentToolContext(
        db=db,
        team_id=team_id,
        user_id=user_id,
        session_id=_optional_int(getattr(session, "id", None)) or envelope.session_id or 0,
        task_id=envelope.task_id,
        workflow_id=workflow_id,
        action_id=action_id,
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE if is_auto_execute else None,
        authorization_source=authorization_source,
        authorization=authorization,
        hitl_decision=None if is_auto_execute else "approve",
        confirmed_by_user=not is_auto_execute,
        auto_execute_authorized=is_auto_execute,
        allowed_tool_names=[tool_name] if tool_name else [],
        allowed_customer_ids=_allowed_customer_ids_for_envelope(envelope),
    )
    registry = AgentToolRegistry(CRMAgentToolService())
    runtime = AgentToolRuntime(registry)

    result = None
    progress_events: list[JSONDict] = []
    if action == "move_opportunity_stage" and tool_name:
        result = await _execute_opportunity_stage_move_plan(
            runtime,
            context,
            envelope.payload,
            envelope.task_key or envelope.action_id,
            progress_events=progress_events,
            event_sink=event_sink,
        )
    elif tool_name and tool_payload:
        result = await runtime.execute(
            tool_name,
            context,
            tool_payload,
            policy=_tool_execution_policy(
                tool_name=tool_name,
                context=context,
                allowed_customer_ids=_allowed_customer_ids_for_envelope(envelope),
            ),
        )
    return ActionToolExecutionResult(result, progress_events)


async def _execute_waiting_task(
    db: Session,
    task,
    session,
    team_id: int,
    user_id: int,
    authorization: str,
    event_sink: AgentRuntimeEventSink | None = None,
):
    envelope = execution_envelope_from_task(task)
    action = envelope.action_type
    payload = envelope.payload
    customer = envelope.customer
    agent_task_crud.update(db, task, AgentTaskUpdate(status=AgentTaskStatus.RUNNING))
    execution = await execute_action_envelope(
        db,
        envelope,
        session=session,
        team_id=team_id,
        user_id=user_id,
        authorization=authorization,
        event_sink=event_sink,
    )
    result = execution.tool_result
    progress_events = execution.progress_events

    if result and result.success:
        agent_task_crud.update(
            db,
            task,
            AgentTaskUpdate(status=AgentTaskStatus.COMPLETED, result_json=result.data),
        )
        current_workflow = envelope.workflow
        if current_workflow:
            workflow_action_ledger.mark_action_executed(
                db,
                workflow=current_workflow,
                team_id=team_id,
                user_id=user_id,
                result=result.data if isinstance(result.data, dict) else {"data": result.data},
                task_id=task.id,
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
                next_target_id = _task_target_id(
                    db,
                    team_id=team_id,
                    target_type="customer",
                    target_id=customer.get("id"),
                )
                next_task = next_waiting_task_projector.project(NextWaitingTaskProjectionRequest(
                    db=db,
                    parent_task=task,
                    team_id=team_id,
                    user_id=user_id,
                    session_id=session.id,
                    spec=NextWaitingTaskSpec(
                        slot="payment_record_after_plan",
                        action="create_payment_record",
                        intent="PAYMENT_RECORD",
                        target_type="customer",
                        target_id=next_target_id,
                        summary="登记本次回款",
                        payload=next_payload,
                        state_context={"customer": customer},
                        required_tools=("create_payment_record",),
                        confirmation_summary="登记本次回款",
                    ),
                )).task
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
        if action == "transition_follow_up_task":
            if isinstance(result.data, dict) and result.data.get("executed") is False:
                results = result.data.get("results")
                first_result = results[0] if isinstance(results, list) and results else {}
                skip_reason = first_result.get("skip_reason") if isinstance(first_result, dict) else None
                return WaitingTaskExecutionResult(
                    result,
                    _follow_up_transition_skip_response(skip_reason),
                    progress_events=progress_events,
                )
            transition_action = payload.get("transition_action")
            if transition_action == "complete":
                return WaitingTaskExecutionResult(result, "任务已标记完成。", progress_events=progress_events)
            if transition_action == "cancel":
                return WaitingTaskExecutionResult(result, "任务已取消。", progress_events=progress_events)
            if transition_action == "delay":
                return WaitingTaskExecutionResult(result, "任务已延期。", progress_events=progress_events)
            if transition_action == "keep_open":
                return WaitingTaskExecutionResult(result, "任务已保持待跟进。", progress_events=progress_events)
            return WaitingTaskExecutionResult(result, "任务状态已更新。", progress_events=progress_events)
        if action == "create_customer_activity" and isinstance(payload.get("_next_task"), dict):
            next_action = payload["_next_task"]
            next_payload = next_action.get("payload") or {}
            next_content = next_action.get("content")
            next_summary = (
                next_content
                if isinstance(next_content, str) and next_content.strip() and "_" not in next_content
                else task_display.readable_action_label(next_action.get("action")) or "等待确认业务操作"
            )
            next_target_id = _task_target_id(
                db,
                team_id=team_id,
                target_type="customer",
                target_id=next_payload.get("customer_id") or customer.get("id"),
            )
            next_tool = _tool_name_for_action(next_action.get("action"))
            next_task = next_waiting_task_projector.project(NextWaitingTaskProjectionRequest(
                db=db,
                parent_task=task,
                team_id=team_id,
                user_id=user_id,
                session_id=session.id,
                spec=NextWaitingTaskSpec(
                    slot="deferred_next_task_after_customer_activity",
                    action=str(next_action.get("action") or ""),
                    intent="CUSTOMER_ACTIVITY",
                    target_type="customer",
                    target_id=next_target_id,
                    summary=next_summary,
                    payload=next_payload,
                    state_context={
                        "customer": next_action.get("customer") or customer,
                        "opportunities": next_action.get("opportunities") or [],
                    },
                    required_tools=(next_tool,) if next_tool else (),
                    confirmation_summary=next_action.get("content") or "等待确认执行下一步动作",
                ),
            )).task
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
    if envelope.workflow:
        workflow_action_ledger.mark_action_failed(
            db,
            workflow=envelope.workflow,
            team_id=team_id,
            user_id=user_id,
            task_id=envelope.task_id,
            error_message=error_message,
            result=coerce_json_dict(result.to_event()) if result else {"success": False, "error": error_message},
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
            policy=_tool_execution_policy(
                tool_name="move_opportunity_stage",
                context=context,
                allowed_customer_ids=[str(payload["customer_id"])] if payload.get("customer_id") else [],
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


def _action_type_from_state(state: JSONDict, workflow: JSONDict) -> str:
    action_type = workflow.get("action_type")
    if isinstance(action_type, str) and action_type.strip():
        return action_type.strip()
    action = state.get("action")
    if isinstance(action, str) and action.strip():
        return action.strip()
    return "unknown"


def _action_id_from_workflow_or_task(*, workflow: JSONDict, task_id: int | None) -> str:
    action_id = workflow.get("action_id")
    if isinstance(action_id, str) and action_id.strip():
        return action_id.strip()
    if task_id is not None:
        return f"task:{task_id}"
    return "task:unknown"


def _payload_from_task_state(*, task: object, state: JSONDict) -> JSONDict:
    state_payload = coerce_json_dict(state.get("payload"))
    if state_payload:
        return state_payload
    task_input = coerce_json_dict(getattr(task, "input_json", None))
    input_payload = coerce_json_dict(task_input.get("payload"))
    if input_payload:
        return input_payload
    input_business_payload = _strip_internal_payload_keys(task_input)
    if input_business_payload:
        return input_business_payload
    return _strip_internal_payload_keys(state)


def _strip_internal_payload_keys(value: JSONDict) -> JSONDict:
    return {
        key: item
        for key, item in value.items()
        if key not in {"action", "workflow", "dependency_json", "customer", "hitl", "opportunities"}
    }


def _allowed_customer_ids_for_envelope(envelope: ActionExecutionEnvelope) -> list[str]:
    customer_id = envelope.customer.get("id") or envelope.payload.get("customer_id")
    if customer_id is None:
        return []
    return [str(customer_id)]


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _payload_has_idempotency_key(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    value = payload.get("idempotency_suffix") or payload.get("idempotency_key")
    return isinstance(value, str) and bool(value.strip())


def _tool_payload_validation_error(tool_name: str | None, payload: object) -> str | None:
    if not tool_name or not isinstance(payload, dict):
        return "invalid_tool_payload:missing_tool_payload"
    try:
        spec = AgentToolRegistry().get(tool_name)
    except KeyError:
        return f"invalid_tool_payload:unregistered_tool:{tool_name}"
    try:
        spec.input_model.model_validate(payload)
    except ValidationError as exc:
        return f"invalid_tool_payload:{_compact_validation_errors(exc)}"
    return None


def _compact_validation_errors(exc: ValidationError) -> str:
    errors: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()) if part is not None)
        message = str(error.get("msg") or "invalid")
        errors.append(f"{loc or 'payload'}:{message}")
        if len(errors) >= 3:
            break
    return ";".join(errors)


def _payload_field_present(payload: object, field: str) -> bool:
    if not isinstance(payload, dict) or not field:
        return False
    current: object = payload
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current.get(part)
    return current not in (None, "")


def _follow_up_transition_skip_response(skip_reason: object) -> str:
    reason = str(skip_reason or "").strip()
    return {
        "TASK_NOT_FOUND": "没有找到这项跟进任务，可能已被删除或你没有访问权限。",
        "TASK_OWNER_MISMATCH": "这项跟进任务不属于你，不能由当前账号标记。",
        "TASK_NOT_OPEN": "这项跟进任务当前不是待跟进状态，不能重复更新。",
        "DELAY_DUE_AT_INVALID": "延期时间无法识别，请补充一个明确的新跟进时间。",
        "TASK_PUBLIC_ID_MISSING": "缺少跟进任务 ID，请从任务卡片中选择具体任务后再确认。",
    }.get(reason, "这项跟进任务暂时没有更新成功，请重新选择任务或补充更明确的信息。")
