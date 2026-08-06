from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.permission import permission_crud
from app.crud.sales_commitment import (
    follow_up_task_crud,
    follow_up_task_projection_run_crud,
    sales_commitment_crud,
)
from app.models.sales_commitment import FollowUpTaskProjectionStatus, FollowUpTaskSourceType
from app.schemas.sales_commitment import FollowUpTaskProjectionRunResponse
from app.services.follow_up_task_projection_service import follow_up_task_projection_service
from app.services.follow_up_task_query_service import follow_up_task_query_service
from app.services.follow_up_task_transition_observability_service import (
    follow_up_task_transition_observability_service,
)
from app.utils.time import business_now

router = APIRouter(prefix="/v1/follow-up-tasks", tags=["客户跟进任务"])
projection_router = APIRouter(prefix="/v1/follow-up-task-projection-runs", tags=["客户跟进任务投影"])
observability_router = APIRouter(prefix="/v1/follow-up-task-transition-observability", tags=["客户跟进任务观测"])


@router.get("", summary="查询我的客户跟进任务")
def list_follow_up_tasks(
    status_filter: str = Query("open", alias="status"),
    due_window: str | None = Query(None),
    customer_id: str | None = Query(None, description="客户 public_id"),
    owner_scope: str = Query("mine", description="mine 只查当前 owner，customer 查客户范围"),
    limit: int = Query(50, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return follow_up_task_query_service.list_tasks(
            db,
            team_id=team_id,
            user_id=current_user.id,
            status=status_filter,
            due_window=due_window,
            customer_public_id=customer_id,
            owner_scope=owner_scope,
            limit=limit,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/customer-arrangements/{customer_id}", summary="查询客户当前跟进安排")
def get_customer_follow_up_arrangement(
    customer_id: str,
    limit: int = Query(20, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
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
    return payload


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
