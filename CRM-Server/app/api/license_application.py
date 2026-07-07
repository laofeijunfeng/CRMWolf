# CRM-Server/app/api/license_application.py
"""License 申请管理 API 端点"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
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
    approve_license_application_full,
    reject_license_application
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
    4. 发送通知给审批人（待 Task A8 泛化实现）
    5. 返回申请信息
    """
    from app.crud.approval import approval_flow_crud, approval_crud
    from app.services.approval_adapter import get_adapter
    from app.constants.business_types import BusinessType

    # 1. 获取申请并验证
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

    # 2. 获取适配器
    adapter = get_adapter(BusinessType.LICENSE)

    # 3. 匹配审批流程
    flow, err = approval_flow_crud.match_flow_generic(
        db,
        BusinessType.LICENSE,
        team_id,
        **adapter.match_kwargs(existing)
    )

    if flow is None and err:
        # CONTRACT 分支：未匹配报错（沿用合同语义）
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err or "未匹配到审批流程"
        )

    if flow is None:
        # PAYMENT/INVOICE 分支：未匹配直通（决策1）
        # License 申请未配置流程时，直接批准（免审批）
        existing.status = LicenseApplicationStatus.ISSUED
        db.commit()
        db.refresh(existing)
        return existing

    # 4. 获取提交人信息
    submitter_id, submitter_name = adapter.get_submitter(existing)

    # 5. 创建审批实例（会自动调用 adapter.on_submit 切换状态）
    try:
        approval = approval_crud.create_approval_generic(
            db,
            BusinessType.LICENSE,
            application_id,
            team_id,
            flow,
            submitter_id,
            submitter_name or current_user.name,  # 补充姓名
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # 6. 发送通知给审批人（待 Task A8 泛化实现）
    # TODO: 调用通知服务发送飞书消息

    # 7. 返回申请信息（状态已由 adapter.on_submit 切换为 PENDING）
    db.refresh(existing)
    return existing


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


@router.post("/{application_id}/approve-full", response_model=LicenseApplicationResponse, summary="审批通过License申请（完整版本）")
def approve_application_full(
    application_id: int,
    approve_data: LicenseApplicationApproveFull,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    审批通过 License 申请（完整版本）

    接收完整的 License 信息文本，解析并填充：
    - enterprise_id: 企业编号
    - supported_modules: 支持模块
    - server_license_code: 服务端 License
    - client_license_code: 客户端 License
    """
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
    return approve_license_application_full(db, team_id, application_id, approve_data, current_user.id)


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
        filename=f"License_{existing.application_number}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )