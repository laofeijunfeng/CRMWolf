# CRM-Server/app/api/deployment.py
"""部署信息管理 API 端点"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import (
    check_customer_edit_permission,
    check_customer_view_permission,
    get_current_active_user,
    get_current_user_team,
)
from app.crud.crud_deployment import (
    create_deployment_info,
    get_deployment_info,
    get_deployment_infos_by_customer,
    update_deployment_info,
    delete_deployment_info,
    set_default_deployment_info
)
from app.schemas.deployment import (
    DeploymentInfoCreate,
    DeploymentInfoUpdate,
    DeploymentInfoResponse
)


router = APIRouter(prefix="/v1/deployment-infos", tags=["部署信息管理"])


@router.post("/", response_model=DeploymentInfoResponse, status_code=status.HTTP_201_CREATED, summary="创建部署信息")
def create_deployment(
    deployment: DeploymentInfoCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """创建部署信息"""
    check_customer_edit_permission(deployment.customer_id, team_id, current_user, db)
    return create_deployment_info(db, team_id, deployment)


@router.get("/", response_model=List[DeploymentInfoResponse], summary="获取客户部署信息列表")
def list_deployments(
    customer_id: int = Query(..., description="客户ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取客户的部署信息列表"""
    check_customer_view_permission(customer_id, team_id, current_user, db)
    return get_deployment_infos_by_customer(db, team_id, customer_id)


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
    return deployment


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
    return updated


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


@router.patch("/{deployment_id}/set-default", response_model=DeploymentInfoResponse, summary="设置默认部署")
def set_default_deployment(
    deployment_id: int,
    customer_id: int = Query(..., description="客户ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """设置默认部署信息"""
    check_customer_edit_permission(customer_id, team_id, current_user, db)
    deployment = set_default_deployment_info(db, team_id, customer_id, deployment_id)
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部署信息不存在"
        )
    return deployment
