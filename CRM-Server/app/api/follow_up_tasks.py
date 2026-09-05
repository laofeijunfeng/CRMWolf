from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.core.list_query import optional_request_list_query, run_or_400
from app.crud.permission import permission_crud
from app.crud.sales_commitment import (
    follow_up_task_confirmation_case_crud,
    follow_up_task_crud,
    follow_up_task_projection_run_crud,
    sales_commitment_crud,
)
from app.models.command_execution import CommandExecutionStatus
from app.models.sales_commitment import (
    FollowUpTaskConfirmationStatus,
    FollowUpTaskProjectionStatus,
    FollowUpTaskSourceType,
)
from app.schemas.sales_commitment import (
    FollowUpTaskConfirmationCaseItemResponse,
    FollowUpTaskConfirmationCaseListResponse,
    FollowUpTaskConfirmationPendingCountResponse,
    FollowUpTaskConfirmationResolveRequest,
    FollowUpTaskConfirmationResolveResponse,
    FollowUpTaskCustomerArrangementResponse,
    FollowUpTaskDetailResponse,
    FollowUpTaskListResponse,
    FollowUpTaskProjectionRunResponse,
)
from app.services.command_execution_service import (
    CommandAlreadyInProgress,
    CommandIdempotencyConflict,
    CommandOperationConflict,
    command_execution_service,
    request_fingerprint,
)
from app.schemas.command import CommandEffect, CommandNextAction, CommandResource
from app.services.follow_up_task_confirmation_channel_service import (
    follow_up_task_confirmation_channel_service,
)
from app.services.follow_up_task_projection_service import follow_up_task_projection_service
from app.services.follow_up_task_query_service import follow_up_task_query_service
from app.services.follow_up_task_reconciliation_evaluation_service import (
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationTaskDecision,
)
from app.services.follow_up_task_transition_execution_service import (
    FollowUpTaskTransitionExecutionStatus,
    follow_up_task_transition_execution_service,
)
from app.services.follow_up_task_transition_observability_service import (
    follow_up_task_transition_observability_service,
)
from app.services.follow_up_task_transition_plan_service import (
    FollowUpTaskTransitionAction,
    FollowUpTaskTransitionActionType,
    FollowUpTaskTransitionPlan,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/follow-up-tasks", tags=["客户跟进任务"])
projection_router = APIRouter(prefix="/v1/follow-up-task-projection-runs", tags=["客户跟进任务投影"])
observability_router = APIRouter(prefix="/v1/follow-up-task-transition-observability", tags=["客户跟进任务观测"])


class FollowUpTaskTransitionRequest(BaseModel):
    action: str = Field(..., description="complete/cancel/postpone")
    proposed_due_at: str | None = Field(None, description="延期后的 ISO 时间")
    reason: str | None = Field(None, max_length=500, description="操作原因")


@router.get("", response_model=FollowUpTaskListResponse, summary="查询我的客户跟进任务")
def list_follow_up_tasks(
    status_filter: str = Query("open", alias="status"),
    due_window: str | None = Query(None),
    customer_id: str | None = Query(None, description="客户 public_id"),
    owner_scope: str = Query("mine", description="mine 只查当前 owner，customer 查客户范围"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    filters: str | None = Query(None, description="通用筛选条件 JSON"),
    sorts: str | None = Query(None, description="通用排序条件 JSON"),
    query_text: str | None = Query(None, description="按待办语义检索的自然语言描述"),
    retrieval_mode: str | None = Query(None, description="structured 或 semantic_filter"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskListResponse:
    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    try:
        payload = run_or_400(lambda: follow_up_task_query_service.list_tasks(
            db,
            team_id=team_id,
            user_id=current_user.id,
            status=status_filter,
            due_window=due_window,
            customer_public_id=customer_id,
            owner_scope=owner_scope,
            skip=skip,
            limit=limit,
            filters=parsed_filters,
            sorts=parsed_sorts,
            query_text=query_text,
            retrieval_mode=retrieval_mode,
        ))
        return FollowUpTaskListResponse.model_validate(payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/confirmation-cases",
    response_model=FollowUpTaskConfirmationCaseListResponse,
    summary="查询我的待确认跟进任务",
)
def list_follow_up_task_confirmation_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskConfirmationCaseListResponse:
    payload = follow_up_task_confirmation_channel_service.list_pending_cases(
        db,
        team_id=team_id,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return FollowUpTaskConfirmationCaseListResponse.model_validate(payload)


@router.get(
    "/confirmation-cases/pending-count",
    response_model=FollowUpTaskConfirmationPendingCountResponse,
    summary="查询我的待确认跟进任务数量",
)
def get_follow_up_task_confirmation_pending_count(
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskConfirmationPendingCountResponse:
    payload = follow_up_task_confirmation_channel_service.list_pending_cases(
        db,
        team_id=team_id,
        user_id=current_user.id,
        limit=1,
    )
    return FollowUpTaskConfirmationPendingCountResponse(count=int(payload["total"]))


@router.get(
    "/confirmation-cases/{case_id}",
    response_model=FollowUpTaskConfirmationCaseItemResponse,
    summary="查询我的待确认跟进任务详情",
)
def get_follow_up_task_confirmation_case(
    case_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskConfirmationCaseItemResponse:
    payload = follow_up_task_confirmation_channel_service.get_pending_case(
        db,
        team_id=team_id,
        user_id=current_user.id,
        case_public_id=case_id,
    )
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待确认事项不存在")
    return FollowUpTaskConfirmationCaseItemResponse.model_validate(payload)


@router.post(
    "/confirmation-cases/{case_id}/resolve",
    response_model=FollowUpTaskConfirmationResolveResponse,
    summary="处理待确认跟进任务",
)
def resolve_follow_up_task_confirmation_case(
    case_id: str,
    request: FollowUpTaskConfirmationResolveRequest,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskConfirmationResolveResponse:
    case = follow_up_task_confirmation_case_crud.get_by_public_id(db, case_id, team_id=team_id)
    if (
        case is None
        or case.owner_id != str(current_user.id)
        or case.status != FollowUpTaskConfirmationStatus.PENDING
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待确认事项不存在")
    payload = follow_up_task_confirmation_channel_service.resolve_reply(
        db,
        team_id=team_id,
        user_id=current_user.id,
        case_public_id=case_id,
        reply_text=request.reply_text,
    )
    return FollowUpTaskConfirmationResolveResponse.model_validate(payload)


@router.get(
    "/customer-arrangements/{customer_id}",
    response_model=FollowUpTaskCustomerArrangementResponse,
    summary="查询客户当前跟进安排",
)
def get_customer_follow_up_arrangement(
    customer_id: str,
    limit: int = Query(20, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskCustomerArrangementResponse:
    try:
        payload = follow_up_task_query_service.list_tasks(
            db,
            team_id=team_id,
            user_id=current_user.id,
            status="open",
            customer_public_id=customer_id,
            owner_scope="customer",
            limit=limit,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    payload["display_policy"] = {
        "surface": "customer_detail_current_follow_up_arrangement",
        "mode": "readonly",
        "task_state_source": "mysql",
        "id_policy": "对外只返回 task/customer public_id；来源活动当前沿用既有客户活动内部ID路由，不作为任务展示字段。",
    }
    return FollowUpTaskCustomerArrangementResponse.model_validate(payload)


@router.get("/{task_id}", response_model=FollowUpTaskDetailResponse, summary="查询客户跟进任务详情")
def get_follow_up_task_detail(
    task_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskDetailResponse:
    try:
        payload = follow_up_task_query_service.get_task_detail(
            db,
            team_id=team_id,
            user_id=current_user.id,
            task_public_id=task_id,
        )
        return FollowUpTaskDetailResponse.model_validate(payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{task_id}/transition", summary="手动更新客户跟进任务状态")
def transition_follow_up_task(
    task_id: str,
    payload: FollowUpTaskTransitionRequest,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
    operation_id: str | None = Header(None, alias="X-Operation-Id"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
) -> dict[str, Any]:
    action_map = {
        "complete": FollowUpTaskTransitionActionType.COMPLETE,
        "cancel": FollowUpTaskTransitionActionType.CANCEL,
        "postpone": FollowUpTaskTransitionActionType.POSTPONE,
    }
    normalized_action = action_map.get(payload.action.lower())
    if normalized_action is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="action 只支持 complete/cancel/postpone")
    if normalized_action == FollowUpTaskTransitionActionType.POSTPONE and not payload.proposed_due_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="延期操作必须提供 proposed_due_at")

    if not isinstance(operation_id, str):
        operation_id = None
    elif not operation_id.strip() or len(operation_id.strip()) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Operation-Id 必须为 1-64 个字符")
    else:
        operation_id = operation_id.strip()
    if not isinstance(idempotency_key, str):
        idempotency_key = None
    elif not idempotency_key.strip() or len(idempotency_key.strip()) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key 必须为 1-128 个字符")
    else:
        idempotency_key = idempotency_key.strip()
    if not isinstance(correlation_id, str):
        correlation_id = None

    task = follow_up_task_crud.get_by_public_id(db, task_id, team_id=team_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    fingerprint = request_fingerprint({
        "task_public_id": task_id,
        "action": normalized_action,
        "proposed_due_at": payload.proposed_due_at,
        "reason": payload.reason or "manual_ui_transition",
    })
    try:
        execution, replay = command_execution_service.begin(
            db,
            team_id=team_id,
            actor_id=str(current_user.id),
            command_type="FOLLOW_UP_TASK_TRANSITION",
            resource_type="FOLLOW_UP_TASK",
            resource_public_id=task_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
    except CommandIdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CommandAlreadyInProgress as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"operation_id": str(exc), "message": "操作正在处理中，请查询操作结果"},
        ) from exc
    except CommandOperationConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if replay:
        db.rollback()
        replay_payload = command_execution_service.to_response_payload(execution)
        stored_data = replay_payload.get("data")
        if isinstance(stored_data, dict):
            return {**stored_data, "operation_id": execution.operation_id, "status": execution.status}
        return replay_payload

    plan = FollowUpTaskTransitionPlan(
        decision=FollowUpTaskReconciliationDecision(
            candidate_public_ids=(task_id,),
            task_decisions=(
                FollowUpTaskReconciliationTaskDecision(
                    decision=normalized_action,
                    confidence=1.0,
                    task_public_id=task_id,
                    proposed_due_at=payload.proposed_due_at,
                ),
            ),
        ),
        actions=(
            FollowUpTaskTransitionAction(
                action=normalized_action,
                task_public_id=task_id,
                confidence=1.0,
                executable=True,
                requires_confirmation=False,
                proposed_due_at=payload.proposed_due_at,
                reason=payload.reason or "manual_ui_transition",
            ),
        ),
        plan_source="manual_ui",
    )
    try:
        result = follow_up_task_transition_execution_service.execute_action(
            db,
            team_id=team_id,
            action=plan.actions[0],
            plan=plan,
            actor_id=str(current_user.id),
            expected_owner_id=str(current_user.id),
            commit=False,
        )
        if result.status != FollowUpTaskTransitionExecutionStatus.EXECUTED:
            command_execution_service.fail(
                db,
                execution,
                error_code=result.skip_reason or "TASK_TRANSITION_FAILED",
                error_message="任务状态未发生变化，请刷新后确认当前状态",
                retryable=False,
            )
            db.commit()
            response_status = (
                status.HTTP_400_BAD_REQUEST
                if result.skip_reason == "TASK_OWNER_MISMATCH"
                else status.HTTP_409_CONFLICT
            )
            raise HTTPException(status_code=response_status, detail=result.skip_reason or "任务状态更新失败")

        task_payload = follow_up_task_query_service.get_task_detail(
            db,
            team_id=team_id,
            user_id=current_user.id,
            task_public_id=task_id,
        )
        data = {"executed": True, "result": result.to_dict(), "task": task_payload}
        command_execution_service.succeed(
            db,
            execution,
            data=data,
            resource=CommandResource(type="FOLLOW_UP_TASK", public_id=task_id),
            effects=[CommandEffect(type="FOLLOW_UP_TASK", public_id=task_id, status="SYNCED")],
            next_actions=[CommandNextAction(id="view-task", label="查看追踪详情", kind="view-detail")],
            correlation_id=correlation_id,
        )
        db.commit()
        return {
            **data,
            "operation_id": execution.operation_id,
            "status": CommandExecutionStatus.SUCCEEDED,
        }
    except HTTPException:
        raise
    except Exception as exc:
        # The domain executor may have committed before an outer failure.  Do
        # not tell the user it is safe to repeat the write; persist UNKNOWN so
        # the client can query the original operation id instead.
        db.rollback()
        try:
            from app.models.command_execution import CommandExecution

            unknown = CommandExecution(
                operation_id=execution.operation_id,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="FOLLOW_UP_TASK_TRANSITION",
                resource_type="FOLLOW_UP_TASK",
                resource_public_id=task_id,
                idempotency_key=idempotency_key.strip() if idempotency_key else None,
                request_fingerprint=fingerprint,
                status=CommandExecutionStatus.UNKNOWN,
                error_code="OUTCOME_UNKNOWN",
                error_message="请求结果暂时无法确认，请查询操作结果",
                retryable=False,
                correlation_id=correlation_id,
                completed_time=business_now(),
            )
            db.add(unknown)
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"operation_id": execution.operation_id, "message": "请求结果暂时无法确认，请查询操作结果"},
        ) from exc


@projection_router.get("/by-activity/{activity_id}", response_model=list[FollowUpTaskProjectionRunResponse], summary="按客户活动查询任务投影运行")
def list_projection_runs_by_activity(
    activity_id: int,
    limit: int = Query(50, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[FollowUpTaskProjectionRunResponse]:
    _ensure_projection_debug_permission(db, team_id=team_id, user_id=current_user.id)
    rows, _ = follow_up_task_projection_run_crud.list_by_source(
        db,
        team_id=team_id,
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        source_activity_id=activity_id,
        limit=limit,
    )
    return [_projection_run_response(db, run, team_id=team_id) for run in rows]


@projection_router.get("/failed", response_model=list[FollowUpTaskProjectionRunResponse], summary="查询失败的任务投影运行")
def list_failed_projection_runs(
    limit: int = Query(50, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[FollowUpTaskProjectionRunResponse]:
    _ensure_projection_debug_permission(db, team_id=team_id, user_id=current_user.id)
    rows, _ = follow_up_task_projection_run_crud.list_failed(
        db,
        team_id=team_id,
        source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
        limit=limit,
    )
    return [_projection_run_response(db, run, team_id=team_id) for run in rows]


@projection_router.post("/{run_id}/retry", response_model=FollowUpTaskProjectionRunResponse, summary="重试失败的任务投影运行")
def retry_projection_run(
    run_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FollowUpTaskProjectionRunResponse:
    _ensure_projection_debug_permission(db, team_id=team_id, user_id=current_user.id)
    run = follow_up_task_projection_run_crud.get_by_public_id(db, run_id, team_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="投影运行不存在")
    if run.status != FollowUpTaskProjectionStatus.FAILED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能重试 FAILED 状态的投影运行")
    try:
        result = follow_up_task_projection_service.retry_projection_run(
            db,
            projection_run_id=run.id,
            actor_id=str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    retry_run = follow_up_task_projection_run_crud.get_by_id(db, result.projection_run_id, team_id)
    if retry_run is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="重试投影运行记录不存在")
    return _projection_run_response(db, retry_run, team_id=team_id)


@observability_router.get("/summary", summary="查询任务状态迁移观测汇总")
def get_transition_observability_summary(
    start_at: datetime | None = Query(None, description="统计开始时间，默认最近 7 天"),
    end_at: datetime | None = Query(None, description="统计结束时间，默认当前业务时间"),
    owner_scope: str = Query("team", description="team 查团队汇总，mine 只查当前用户 owner"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ensure_projection_debug_permission(db, team_id=team_id, user_id=current_user.id)
    resolved_end_at = end_at or business_now()
    resolved_start_at = start_at or (resolved_end_at - timedelta(days=7))
    if resolved_start_at >= resolved_end_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_at 必须早于 end_at")
    if owner_scope not in {"team", "mine"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="owner_scope 只支持 team 或 mine")

    summary = follow_up_task_transition_observability_service.summarize(
        db,
        team_id=team_id,
        start_at=resolved_start_at,
        end_at=resolved_end_at,
        owner_id=str(current_user.id) if owner_scope == "mine" else None,
    )
    payload = summary.to_dict()
    payload["filters"] = {"owner_scope": owner_scope}
    return payload


def _ensure_projection_debug_permission(db: Session, *, team_id: int, user_id: int) -> None:
    permission_codes = {permission.code for permission in permission_crud.get_user_permissions(db, user_id, team_id)}
    if permission_codes.intersection(
        {
            "follow_up_task:view:team",
            "follow_up_task:view:all",
            "follow_up_task:operate:all",
            "follow_up_task:edit:all",
        }
    ):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="缺少任务投影排查权限")


def _projection_run_response(db: Session, run, *, team_id: int) -> FollowUpTaskProjectionRunResponse:
    return FollowUpTaskProjectionRunResponse.from_model(
        run,
        created_task_public_ids=follow_up_task_crud.list_public_ids_by_ids(
            db,
            team_id=team_id,
            task_ids=run.created_task_ids_json or [],
        ),
        updated_task_public_ids=follow_up_task_crud.list_public_ids_by_ids(
            db,
            team_id=team_id,
            task_ids=run.updated_task_ids_json or [],
        ),
        cancelled_task_public_ids=follow_up_task_crud.list_public_ids_by_ids(
            db,
            team_id=team_id,
            task_ids=run.cancelled_task_ids_json or [],
        ),
        created_commitment_public_ids=sales_commitment_crud.list_public_ids_by_ids(
            db,
            team_id=team_id,
            commitment_ids=run.created_commitment_ids_json or [],
        ),
        updated_commitment_public_ids=sales_commitment_crud.list_public_ids_by_ids(
            db,
            team_id=team_id,
            commitment_ids=run.updated_commitment_ids_json or [],
        ),
    )
