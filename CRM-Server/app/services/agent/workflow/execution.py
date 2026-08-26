"""Guarded CRM effects owned by the durable Workflow subgraph."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Protocol, cast

import httpx
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent import action_workflow
from app.services.agent.guardrails import AgentToolExecutionPolicy, AgentToolGuardrailError
from app.services.agent.tool_registry import agent_tool_registry
from app.services.agent.tools.api_client import CRMAPIClientError
from app.services.agent.tools.base import AgentToolContext, AgentToolResult
from app.services.agent.workflow.contracts import (
    WorkflowActionPlan,
    WorkflowCommand,
    WorkflowEffectResult,
    WorkflowRuntimeContext,
    WorkflowTurnInput,
)
from app.services.agent.workflow.resources import (
    CRMFollowUpTaskConfirmationCaseResolver,
    CRMFollowUpTaskResolver,
    CRMOpportunityStageResolver,
    FollowUpTaskConfirmationCaseResolver,
    FollowUpTaskResolver,
    OpportunityStageResolver,
    WorkflowResourceResolutionError,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class WorkflowToolRegistry(Protocol):
    async def execute(
        self,
        name: str,
        context: AgentToolContext,
        payload: dict[str, object],
        *,
        policy: AgentToolExecutionPolicy,
    ) -> AgentToolResult: ...


class CRMWorkflowEffectExecutor:
    """Execute one confirmed ordered command plan through CRM tool guardrails."""

    def __init__(
        self,
        *,
        tool_registry: WorkflowToolRegistry | None = None,
        follow_up_task_resolver: FollowUpTaskResolver | None = None,
        follow_up_confirmation_case_resolver: FollowUpTaskConfirmationCaseResolver | None = None,
        opportunity_stage_resolver: OpportunityStageResolver | None = None,
    ) -> None:
        self._tool_registry = tool_registry or agent_tool_registry
        self._follow_up_task_resolver = follow_up_task_resolver or CRMFollowUpTaskResolver()
        self._follow_up_confirmation_case_resolver = (
            follow_up_confirmation_case_resolver or CRMFollowUpTaskConfirmationCaseResolver()
        )
        self._opportunity_stage_resolver = opportunity_stage_resolver or CRMOpportunityStageResolver()

    async def execute(
        self,
        plan: WorkflowActionPlan,
        *,
        workflow_id: str,
        request: WorkflowTurnInput,
        runtime: WorkflowRuntimeContext,
    ) -> WorkflowEffectResult:
        unsupported = next(
            (
                command
                for command in plan.commands
                if not _is_supported_write_command(command, plan.execution_authorization)
            ),
            None,
        )
        if unsupported is not None:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_ACTION_UNSUPPORTED",
                message="当前工作流尚不能执行这个写入动作。",
            )

        execution_context = _execution_context(request, runtime)
        if isinstance(execution_context, WorkflowEffectResult):
            return execution_context
        db, authorization, team_id, user_id, session_id = execution_context
        command_results: dict[str, object] = {}
        durable_work = []

        for command in plan.commands:
            try:
                payload = _resolve_command_payload(command, command_results)
            except ValueError:
                return WorkflowEffectResult(
                    success=False,
                    code="WORKFLOW_COMMAND_BINDING_FAILED",
                    message="工作流命令结果无法传递到后续操作。",
                )
            payload["idempotency_suffix"] = f"{workflow_id}:{command.command_id}"
            try:
                allowed_customer_ids = _resolve_authorized_customer_ids(command, command_results)
            except ValueError:
                return WorkflowEffectResult(
                    success=False,
                    code="WORKFLOW_AUTHORIZATION_SCOPE_INVALID",
                    message="工作流授权范围无法验证。",
                )
            resource_validation = await self._validate_command_resources(
                command,
                payload=payload,
                authorization=authorization,
                user_id=user_id,
                allowed_customer_ids=allowed_customer_ids,
            )
            if resource_validation is not None:
                return resource_validation
            command_action_id = f"{plan.action_id}:{command.command_id}"
            if plan.execution_authorization == "CONFIRMATION_REQUIRED":
                execution_policy = action_workflow.EXECUTION_REQUIRES_CONFIRMATION
                authorization_source = "workflow_structured_confirmation"
                hitl_decision = "approve"
                confirmed_by_user = True
                auto_execute_authorized = False
            elif plan.execution_authorization == "AUTO_EXECUTE_AUTHORIZED":
                execution_policy = "auto_execute"
                authorization_source = "semantic_auto_execute_low_risk"
                hitl_decision = None
                confirmed_by_user = False
                auto_execute_authorized = True
            else:
                execution_policy = None
                authorization_source = "workflow_resume_authorized"
                hitl_decision = None
                confirmed_by_user = False
                auto_execute_authorized = False
            context = AgentToolContext(
                db=db,
                team_id=team_id,
                user_id=user_id,
                session_id=session_id,
                authorization=authorization,
                workflow_id=workflow_id,
                action_id=command_action_id,
                execution_policy=execution_policy,
                authorization_source=authorization_source,
                hitl_decision=hitl_decision,
                confirmed_by_user=confirmed_by_user,
                auto_execute_authorized=auto_execute_authorized,
                allowed_tool_names=[command.tool_name],
                allowed_customer_ids=allowed_customer_ids,
                deadline_at=runtime.deadline_at,
            )
            policy = AgentToolExecutionPolicy(
                hitl_decision=hitl_decision,
                execution_policy=execution_policy,
                workflow_id=workflow_id,
                action_id=command_action_id,
                authorization_source=authorization_source,
                auto_execute_authorized=auto_execute_authorized,
                allowed_tool_names=[command.tool_name],
                allowed_customer_ids=allowed_customer_ids,
            )
            result = await self._execute_command(command, context=context, payload=payload, policy=policy)
            if isinstance(result, WorkflowEffectResult):
                return result
            command_results[command.command_id] = result.data
            durable_work.extend(result.durable_work)

        return WorkflowEffectResult(
            success=True,
            message=plan.completed_text,
            durable_work=durable_work,
        )

    async def _validate_command_resources(
        self,
        command: WorkflowCommand,
        *,
        payload: dict[str, object],
        authorization: str,
        user_id: int,
        allowed_customer_ids: list[str],
    ) -> WorkflowEffectResult | None:
        if command.tool_name == "resolve_follow_up_task_confirmation_case":
            return await self._validate_follow_up_confirmation_case(
                payload=payload,
                authorization=authorization,
                user_id=user_id,
                allowed_customer_ids=allowed_customer_ids,
            )
        if command.tool_name == "transition_follow_up_task":
            return await self._validate_follow_up_task_transition(
                payload=payload,
                authorization=authorization,
                user_id=user_id,
                allowed_customer_ids=allowed_customer_ids,
            )
        if command.tool_name != "move_opportunity_stage":
            return None
        opportunity_id = payload.get("opportunity_id")
        stage_template_id = payload.get("stage_template_id")
        if (
            len(allowed_customer_ids) != 1
            or not isinstance(opportunity_id, str)
            or not opportunity_id
            or not isinstance(stage_template_id, int)
            or isinstance(stage_template_id, bool)
            or stage_template_id <= 0
        ):
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_AUTHORIZATION_SCOPE_INVALID",
                message="工作流授权范围无法验证。",
            )
        try:
            resolution = await self._opportunity_stage_resolver.resolve(
                customer_id=allowed_customer_ids[0],
                authorization=authorization,
                opportunity_id=None,
                opportunity_reference_text=None,
                target_stage_name=None,
                selected_opportunity_id=opportunity_id,
                selected_stage_id=stage_template_id,
            )
        except WorkflowResourceResolutionError as exc:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_RESOURCE_REVALIDATION_FAILED",
                message=exc.message,
                retryable=exc.retryable,
            )
        if (
            resolution.status != "RESOLVED"
            or resolution.opportunity is None
            or resolution.opportunity.opportunity_id != opportunity_id
            or resolution.target_stage is None
            or resolution.target_stage.stage_template_id != stage_template_id
        ):
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_RESOURCE_STALE",
                message="商机或采购阶段已变化,请重新发起操作。",
            )
        return None

    async def _validate_follow_up_confirmation_case(
        self,
        *,
        payload: dict[str, object],
        authorization: str,
        user_id: int,
        allowed_customer_ids: list[str],
    ) -> WorkflowEffectResult | None:
        case_id = payload.get("case_id")
        reply_text = payload.get("reply_text")
        resolver = self._follow_up_confirmation_case_resolver
        if (
            resolver is None
            or not isinstance(case_id, str)
            or not case_id
            or not isinstance(reply_text, str)
            or not reply_text.strip()
        ):
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_AUTHORIZATION_SCOPE_INVALID",
                message="工作流授权范围无法验证。",
            )
        try:
            resolution = await resolver.resolve(
                authorization=authorization,
                user_id=user_id,
                case_id=case_id,
            )
        except WorkflowResourceResolutionError as exc:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_RESOURCE_REVALIDATION_FAILED",
                message=exc.message,
                retryable=exc.retryable,
            )
        case = resolution.case
        if (
            resolution.status != "RESOLVED"
            or case is None
            or case.case_id != case_id
            or case.owner_id != str(user_id)
            or case.status != "PENDING"
        ):
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_RESOURCE_STALE",
                message="待确认事项已变化或已处理,请重新发起操作。",
            )
        expected_customer_ids = [case.customer_id] if case.customer_id is not None else []
        if allowed_customer_ids != expected_customer_ids:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_AUTHORIZATION_SCOPE_INVALID",
                message="工作流授权范围无法验证。",
            )
        return None

    async def _validate_follow_up_task_transition(
        self,
        *,
        payload: dict[str, object],
        authorization: str,
        user_id: int,
        allowed_customer_ids: list[str],
    ) -> WorkflowEffectResult | None:
        task_id = payload.get("task_id")
        action = payload.get("action")
        proposed_due_at = payload.get("proposed_due_at")
        if (
            not isinstance(task_id, str)
            or not task_id
            or action not in {"complete", "cancel", "postpone"}
            or (action == "postpone" and (not isinstance(proposed_due_at, str) or not proposed_due_at))
        ):
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_AUTHORIZATION_SCOPE_INVALID",
                message="工作流授权范围无法验证。",
            )
        try:
            resolution = await self._follow_up_task_resolver.resolve(
                authorization=authorization,
                user_id=user_id,
                task_id=task_id,
            )
        except WorkflowResourceResolutionError as exc:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_RESOURCE_REVALIDATION_FAILED",
                message=exc.message,
                retryable=exc.retryable,
            )
        if (
            resolution.status != "RESOLVED"
            or resolution.task is None
            or resolution.task.task_id != task_id
            or resolution.task.owner_id != str(user_id)
            or resolution.task.status != "open"
        ):
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_RESOURCE_STALE",
                message="跟进任务已变化或不再可更新,请重新发起操作。",
            )
        expected_customer_ids = (
            [resolution.task.customer_id] if resolution.task.customer_id is not None else []
        )
        if allowed_customer_ids != expected_customer_ids:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_AUTHORIZATION_SCOPE_INVALID",
                message="工作流授权范围无法验证。",
            )
        return None

    async def _execute_command(
        self,
        command: WorkflowCommand,
        *,
        context: AgentToolContext,
        payload: dict[str, object],
        policy: AgentToolExecutionPolicy,
    ) -> AgentToolResult | WorkflowEffectResult:
        try:
            result = await self._tool_registry.execute(
                command.tool_name,
                context,
                payload,
                policy=policy,
            )
        except AgentToolGuardrailError:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_AUTHORIZATION_REJECTED",
                message="工作流执行授权校验失败, 请重新确认后再试。",
            )
        except ValidationError:
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_PAYLOAD_INVALID",
                message="工作流写入数据无效, 请补充或修正后重试。",
            )
        except CRMAPIClientError as exc:
            retryable = _is_retryable_status(exc.status_code)
            return WorkflowEffectResult(
                success=False,
                code=("WORKFLOW_CRM_API_UNAVAILABLE" if retryable else "WORKFLOW_CRM_API_REJECTED"),
                message=("CRM 服务暂时不可用, 请稍后重试。" if retryable else exc.message),
                retryable=retryable,
            )
        except (httpx.TimeoutException, httpx.HTTPError, SQLAlchemyError):
            return WorkflowEffectResult(
                success=False,
                code="WORKFLOW_DEPENDENCY_UNAVAILABLE",
                message="工作流依赖服务暂时不可用, 请稍后重试。",
                retryable=True,
            )
        if result.success:
            return result
        return WorkflowEffectResult(
            success=False,
            code="WORKFLOW_TOOL_REJECTED",
            message=result.error_message or "业务操作失败, 请检查业务数据后重试。",
            retryable=_is_retryable_status(result.status_code),
        )


def _is_supported_write_command(
    command: WorkflowCommand,
    execution_authorization: str,
) -> bool:
    capability = action_workflow.action_capability(command.tool_name)
    if (
        capability.tool_name != command.tool_name
        or not capability.is_write
        or not capability.requires_user_authorization
    ):
        return False
    if execution_authorization == "CONFIRMATION_REQUIRED":
        return capability.requires_confirmation
    if execution_authorization == "AUTO_EXECUTE_AUTHORIZED":
        return command.tool_name == "create_customer_activity"
    if execution_authorization == "RESUME_AUTHORIZED":
        return not capability.requires_confirmation
    return False


def _execution_context(
    request: WorkflowTurnInput,
    runtime: WorkflowRuntimeContext,
) -> tuple[Session, str, int, int, int] | WorkflowEffectResult:
    db = runtime.db
    authorization = runtime.authorization
    if db is None or not isinstance(authorization, str) or not authorization:
        return WorkflowEffectResult(
            success=False,
            code="WORKFLOW_EXECUTION_CONTEXT_MISSING",
            message="工作流执行上下文不完整, 请稍后重试。",
            retryable=True,
        )
    team_id = request.principal.team_id
    user_id = request.principal.user_id
    session_id = request.principal.session_id
    return (
        cast("Session", db),
        authorization,
        cast("int", team_id),
        cast("int", user_id),
        cast("int", session_id),
    )


def _resolve_command_payload(
    command: WorkflowCommand,
    command_results: dict[str, object],
) -> dict[str, object]:
    payload = cast("dict[str, object]", deepcopy(command.payload))
    for binding in command.bindings:
        if binding.source_command_id not in command_results:
            raise ValueError("binding source command has no result")
        value = _read_path(
            command_results[binding.source_command_id],
            binding.source_path,
        )
        _write_path(payload, binding.target_path, value)
    return payload


def _read_path(value: object, path: list[str]) -> object:
    current = value
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            raise ValueError("binding source path does not exist")
        current = current[segment]
    if current is None:
        raise ValueError("binding source value is null")
    return deepcopy(current)


def _write_path(payload: dict[str, object], path: list[str], value: object) -> None:
    current = payload
    for segment in path[:-1]:
        existing = current.get(segment)
        if existing is None:
            nested: dict[str, object] = {}
            current[segment] = nested
            current = nested
            continue
        if not isinstance(existing, dict):
            raise ValueError("binding target path crosses a scalar value")
        current = existing
    current[path[-1]] = value


def _resolve_authorized_customer_ids(
    command: WorkflowCommand,
    command_results: dict[str, object],
) -> list[str]:
    values = list(command.authorization_scope.customer_ids)
    for binding in command.authorization_scope.customer_bindings:
        if binding.source_command_id not in command_results:
            raise ValueError("authorization binding source command has no result")
        value = _read_path(command_results[binding.source_command_id], binding.source_path)
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ValueError("authorization binding must resolve to a customer id")
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("authorization customer id cannot be empty")
        values.append(normalized)
    return list(dict.fromkeys(values))


def _is_retryable_status(status_code: int | None) -> bool:
    return status_code is None or status_code in {408, 429} or status_code >= 500
