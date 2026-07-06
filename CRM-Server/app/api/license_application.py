# CRM-Server/app/api/license_application.py
"""License 申请管理 API 端点"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.crud_license_application import (
    create_license_application,
    get_license_application,
    get_license_applications_by_customer,
    update_license_application,
    delete_license_application,
    submit_license_application,
    approve_license_application,
    reject_license_application
)
from app.schemas.license_application import (
    LicenseApplicationCreate,
    LicenseApplicationUpdate,
    LicenseApplicationApprove,
    LicenseApplicationResponse
)
from app.models.license_application import LicenseApplicationStatus


router = APIRouter(prefix="/v1/license-applications", tags=["License申请管理"])


@router.post("/", response_model=LicenseApplicationResponse, status_code=status.HTTP_201_CREATED, summary="创建License申请")
def create_application(
    application: LicenseApplicationCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """创建 License 申请（草稿状态）"""
    return create_license_application(db, team_id, application, current_user.id)


@router.get("/", response_model=List[LicenseApplicationResponse], summary="获取客户License申请列表")
def list_applications(
    customer_id: int = Query(..., description="客户ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取客户的 License 申请列表"""
    return get_license_applications_by_customer(db, team_id, customer_id)


@router.get("/{application_id}", response_model=LicenseApplicationResponse, summary="获取License申请详情")
def get_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取 License 申请详情"""
    application = get_license_application(db, team_id, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    return application


@router.put("/{application_id}", response_model=LicenseApplicationResponse, summary="更新License申请")
def update_application(
    application_id: int,
    application: LicenseApplicationUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新 License 申请（仅草稿状态可编辑）"""
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅草稿状态的申请可以编辑"
        )
    return update_license_application(db, team_id, application_id, application)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除License申请")
def delete_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """删除 License 申请（仅草稿状态可删除）"""
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅草稿状态的申请可以删除"
        )
    delete_license_application(db, team_id, application_id)


@router.post("/{application_id}/submit", response_model=LicenseApplicationResponse, summary="提交License申请")
def submit_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """提交 License 申请（草稿 → 待审批）"""
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅草稿状态的申请可以提交"
        )
    return submit_license_application(db, team_id, application_id)


@router.post("/{application_id}/approve", response_model=LicenseApplicationResponse, summary="审批通过License申请")
def approve_application(
    application_id: int,
    approve_data: LicenseApplicationApprove,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """审批通过 License 申请（待审批 → 已发放）"""
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅待审批状态的申请可以审批"
        )
    return approve_license_application(db, team_id, application_id, approve_data, current_user.id)


@router.post("/{application_id}/reject", response_model=LicenseApplicationResponse, summary="审批拒绝License申请")
def reject_application(
    application_id: int,
    reason: str = Query(..., description="拒绝原因"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """审批拒绝 License 申请（待审批 → 已驳回）"""
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅待审批状态的申请可以拒绝"
        )
    return reject_license_application(db, team_id, application_id, reason)