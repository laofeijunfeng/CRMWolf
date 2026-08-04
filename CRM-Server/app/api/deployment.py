"""部署信息管理 API 端点"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    check_customer_edit_permission,
    check_customer_view_permission,
    get_current_active_user,
    get_current_user_team,
)
from app.crud.crud_deployment import (
    create_deployment_info,
    delete_deployment_info,
    get_deployment_info,
    get_deployment_infos_by_customer,
    set_default_deployment_info,
    update_deployment_info,
)
from app.models.deployment import DeploymentInfo
from app.schemas.deployment import (
    DeploymentInfoCreate,
    DeploymentInfoResponse,
    DeploymentInfoUpdate,
)
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeType,
    customer_business_object_intelligence_service,
)

router = APIRouter(prefix="/v1/deployment-infos", tags=["部署信息管理"])


def _deployment_response(deployment: DeploymentInfo) -> DeploymentInfoResponse:
    if not deployment.customer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="部署信息关联客户数据异常",
        )
    return DeploymentInfoResponse(**{
        "id": deployment.id,
        "customer_id": deployment.customer.public_id,
        "team_id": deployment.team_id,
        "deployment_name": deployment.deployment_name,
        "server_address": deployment.server_address,
        "authorized_users": deployment.authorized_users,
        "is_default": deployment.is_default,
        "created_time": deployment.created_time,
        "last_modified_time": deployment.last_modified_time,
    })


def _enqueue_deployment_intelligence_refresh(
    db: Session,
    deployment: DeploymentInfo,
    *,
    change_type: CustomerBusinessObjectChangeType,
    actor_id: str | None,
) -> None:
    customer_business_object_intelligence_service.enqueue_object_change_refresh(
        db,
        source_type="deployment_info",
        business_object=deployment,
        change_type=change_type,
        actor_id=actor_id,
    )


@router.post("/", response_model=DeploymentInfoResponse, status_code=status.HTTP_201_CREATED, summary="创建部署信息")
def create_deployment(
    deployment: DeploymentInfoCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """创建部署信息"""
    customer = check_customer_edit_permission(deployment.customer_id, team_id, current_user, db)
    deployment = deployment.model_copy(update={"customer_id": customer.id})
    created = create_deployment_info(db, team_id, deployment)
    _enqueue_deployment_intelligence_refresh(
        db,
        created,
        change_type="created",
        actor_id=str(current_user.id),
    )
    return _deployment_response(created)


@router.get("/", response_model=List[DeploymentInfoResponse], summary="获取客户部署信息列表")
def list_deployments(
    customer_id: str = Query(..., description="客户对外ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取客户的部署信息列表"""
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    deployments = get_deployment_infos_by_customer(db, team_id, customer.id)
    return [_deployment_response(deployment) for deployment in deployments]


@router.get("/{deployment_id}", response_model=DeploymentInfoResponse, summary="获取部署信息详情")
def get_deployment(
    deployment_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取部署信息详情"""
    deployment = get_deployment_info(db, team_id, deployment_id)
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部署信息不存在"
        )
    check_customer_view_permission(deployment.customer_id, team_id, current_user, db)
    return _deployment_response(deployment)


@router.put("/{deployment_id}", response_model=DeploymentInfoResponse, summary="更新部署信息")
def update_deployment(
    deployment_id: int,
    deployment: DeploymentInfoUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新部署信息"""
    existing = get_deployment_info(db, team_id, deployment_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部署信息不存在"
        )
    check_customer_edit_permission(existing.customer_id, team_id, current_user, db)
    updated = update_deployment_info(db, team_id, deployment_id, deployment)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部署信息不存在"
        )
    _enqueue_deployment_intelligence_refresh(
        db,
        updated,
        change_type="updated",
        actor_id=str(current_user.id),
    )
    return _deployment_response(updated)


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除部署信息")
def delete_deployment(
    deployment_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """删除部署信息（软删除）"""
    deployment = get_deployment_info(db, team_id, deployment_id)
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部署信息不存在"
        )
    check_customer_edit_permission(deployment.customer_id, team_id, current_user, db)
    if not delete_deployment_info(db, team_id, deployment_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部署信息不存在"
        )
    _enqueue_deployment_intelligence_refresh(
        db,
        deployment,
        change_type="deleted",
        actor_id=str(current_user.id),
    )


@router.patch("/{deployment_id}/set-default", response_model=DeploymentInfoResponse, summary="设置默认部署")
def set_default_deployment(
    deployment_id: int,
    customer_id: str = Query(..., description="客户对外ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """设置默认部署信息"""
    customer = check_customer_edit_permission(customer_id, team_id, current_user, db)
    deployment = set_default_deployment_info(db, team_id, customer.id, deployment_id)
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部署信息不存在"
        )
    _enqueue_deployment_intelligence_refresh(
        db,
        deployment,
        change_type="updated",
        actor_id=str(current_user.id),
    )
    return _deployment_response(deployment)
