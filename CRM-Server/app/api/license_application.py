# CRM-Server/app/api/license_application.py
"""License 申请管理 API 端点"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from urllib.parse import quote
import os

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team, require_permission
from app.crud.crud_license_application import (
    create_license_application,
    get_license_application,
    get_license_applications_by_customer,
    update_license_application,
    delete_license_application,
    submit_license_application,
    issue_license_application_full,
)
from app.schemas.license_application import (
    LicenseApplicationCreate,
    LicenseApplicationUpdate,
    LicenseApplicationApprove,
    LicenseApplicationApproveFull,
    LicenseApplicationResponse
)
from app.models.license_application import LicenseApplicationStatus
from app.services.license_export_service import export_license_document


router = APIRouter(prefix="/v1/license-applications", tags=["License申请管理"])


def _content_disposition(filename: str) -> str:
    safe_filename = os.path.basename(filename).replace("\r", "").replace("\n", "")
    fallback_name = safe_filename.encode("ascii", "ignore").decode("ascii") or "license_file.docx"
    quoted_name = quote(safe_filename, safe="")
    return f"attachment; filename=\"{fallback_name}\"; filename*=UTF-8''{quoted_name}"


def _sanitize_filename_part(value: str) -> str:
    return value.translate(str.maketrans('', '', '\\/:*?"<>|\r\n')).strip()


def _export_filename(application) -> str:
    customer_name = application.customer.account_name if application.customer else "客户"
    safe_customer_name = _sanitize_filename_part(customer_name) or "客户"
    current_date = datetime.now().strftime("%Y%m%d")
    return f"私有化部署License-{safe_customer_name}_{current_date}.docx"


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
    applications, _ = get_license_applications_by_customer(db, team_id, customer_id)
    return applications


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
    """
    提交 License 申请（接入审批引擎）

    流程：
    1. 验证申请存在且状态为 DRAFT
    2. 匹配审批流程（按 license_type）
    3. 创建审批实例（Approval + ApprovalRecord）
    4. 发送通知给审批人（待实现）
    5. 返回申请信息
    """
    from app.crud.crud_license_application import license_application_crud

    # 获取提交人信息
    submitter_id = str(current_user.id)
    submitter_name = current_user.name

    try:
        application = license_application_crud.submit(
            db,
            team_id,
            application_id,
            submitter_id,
            submitter_name
        )
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="License申请不存在"
            )
        return application
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{application_id}/approve", response_model=LicenseApplicationResponse, summary="[已废弃] 审批通过License申请", deprecated=True)
def approve_application(
    application_id: int,
    approve_data: LicenseApplicationApprove,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="该接口已废弃。请使用 /v1/approvals/LICENSE/{application_id}/approve 进行审批。",
    )


@router.post("/{application_id}/approve-full", response_model=LicenseApplicationResponse, summary="[已废弃] 审批通过License申请（完整版本）", deprecated=True)
def approve_application_full(
    application_id: int,
    approve_data: LicenseApplicationApproveFull,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="该接口已废弃。请先使用通用审批接口完成审批，再调用 /v1/license-applications/{application_id}/issue 发放License。",
    )


@router.post("/{application_id}/reject", response_model=LicenseApplicationResponse, summary="[已废弃] 审批拒绝License申请", deprecated=True)
def reject_application(
    application_id: int,
    reason: str = Query(..., description="拒绝原因"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="该接口已废弃。请使用 /v1/approvals/LICENSE/{application_id}/approve 提交 REJECT 动作。",
    )


@router.post("/{application_id}/issue", response_model=LicenseApplicationResponse, summary="发放License申请")
def issue_application(
    application_id: int,
    issue_data: LicenseApplicationApproveFull,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("license:issue")),
    db: Session = Depends(get_db)
):
    """发放已通过审批的 License 申请。"""
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"License申请状态为 {existing.status}，不可发放"
        )
    try:
        issued = issue_license_application_full(db, team_id, application_id, issue_data, str(current_user.id))
        if not issued:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="License申请不存在"
            )
        return issued
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{application_id}/export", summary="导出License文档")
def export_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    导出 License Word 文档

    仅已发放状态的申请可以导出，文件名格式：
    私有化{试用/正式}License-{客户名称}_{当前日期}.docx
    """
    existing = get_license_application(db, team_id, application_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="License申请不存在"
        )
    if existing.status != LicenseApplicationStatus.ISSUED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅已发放状态的申请可以导出"
        )

    # 导出 Word 文档
    file_path = export_license_document(existing)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": _content_disposition(_export_filename(existing))
        }
    )
