from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from typing import Optional
import os

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_permission, get_current_user_team
from app.models.user import User
from app.models.customer import Customer
from app.models.contract import Contract
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan
from app.schemas.invoice import (
    InvoiceTitleCreate, InvoiceTitleUpdate, InvoiceTitleResponse,
    InvoiceApplicationCreate, InvoiceApplicationUpdate, InvoiceApplicationResponse,
    MessageResponse,
    InvoiceTitleListResponse, InvoiceApplicationListResponse, PaymentPlanInvoiceSummary
)
from app.crud.invoice import invoice_title_crud, invoice_application_crud
from app.services.file_storage import file_storage_service, FileStorageError

router = APIRouter(prefix="/invoice-titles", tags=["开票抬头管理"])


@router.post("", response_model=InvoiceTitleResponse, summary="添加开票抬头", description="为指定客户添加开票抬头信息")
def create_invoice_title(
    customer_id: int = Query(..., description="客户ID"),
    title_data: InvoiceTitleCreate = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:title:create")),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.team_id == team_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    existing_title = invoice_title_crud.get_by_taxpayer_id(db, customer_id, title_data.taxpayer_id, team_id)
    if existing_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该纳税人识别号已存在"
        )

    title = invoice_title_crud.create(db, customer_id, title_data, team_id)
    return title


@router.get("", response_model=InvoiceTitleListResponse, summary="查询开票抬头列表", description="获取指定客户的所有开票抬头")
def list_invoice_titles(
    customer_id: int = Query(..., description="客户ID"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    titles = invoice_title_crud.get_by_customer_id(db, customer_id, team_id)
    return {"invoice_titles": titles}


@router.get("/{title_id}", response_model=InvoiceTitleResponse, summary="获取开票抬头详情", description="获取指定开票抬头的详细信息")
def get_invoice_title(
    title_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    title = invoice_title_crud.get_by_id(db, title_id, team_id)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="开票抬头不存在"
        )
    return title


@router.put("/{title_id}", response_model=InvoiceTitleResponse, summary="修改开票抬头", description="修改指定的开票抬头信息")
def update_invoice_title(
    title_id: int,
    title_data: InvoiceTitleUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:title:edit")),
    db: Session = Depends(get_db)
):
    title = invoice_title_crud.get_by_id(db, title_id, team_id)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="开票抬头不存在"
        )

    updated_title = invoice_title_crud.update(db, title, title_data)
    return updated_title


@router.patch("/{title_id}/set-default", response_model=InvoiceTitleResponse, summary="设置默认抬头", description="设置指定的开票抬头为默认抬头，自动取消原默认抬头")
def set_default_invoice_title(
    title_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:title:set_default")),
    db: Session = Depends(get_db)
):
    title = invoice_title_crud.get_by_id(db, title_id, team_id)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="开票抬头不存在"
        )

    updated_title = invoice_title_crud.set_default(db, title.customer_id, title_id, team_id)
    if not updated_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="设置默认抬头失败"
        )
    return updated_title


@router.delete("/{title_id}", response_model=MessageResponse, summary="删除开票抬头", description="删除指定的开票抬头")
def delete_invoice_title(
    title_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:title:delete")),
    db: Session = Depends(get_db)
):
    success = invoice_title_crud.delete(db, title_id, team_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="开票抬头不存在"
        )
    return {"message": "删除成功"}


invoice_router = APIRouter(prefix="/invoice-applications", tags=["发票申请管理"])


@invoice_router.post("", response_model=InvoiceApplicationResponse, summary="创建发票申请", description="创建新的发票申请，自动关联业务上下文（客户、合同、商机、回款计划）")
def create_invoice_application(
    application_data: InvoiceApplicationCreate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        application = invoice_application_crud.create(
            db,
            application_data,
            str(current_user.id),
            team_id
        )
        return _populate_application_info(db, application, team_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@invoice_router.get("", response_model=InvoiceApplicationListResponse, summary="查询发票申请列表", description="支持按客户、合同、状态等多条件筛选发票申请")
def list_invoice_applications(
    customer_id: Optional[int] = Query(None, description="客户ID"),
    contract_id: Optional[int] = Query(None, description="合同ID"),
    status: Optional[str] = Query(None, description="申请状态"),
    applicant_id: Optional[str] = Query(None, description="申请人ID"),
    me: bool = Query(False, description="是否只查询当前用户负责的客户的数据"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    current_user_id = str(current_user.id) if me else None

    applications, total = invoice_application_crud.list_applications(
        db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        customer_id=customer_id,
        contract_id=contract_id,
        status=status,
        applicant_id=applicant_id,
        current_user_id=current_user_id
    )

    populated_applications = [_populate_application_info(db, app, team_id) for app in applications]

    # 计算页码（skip/limit + 1）
    current_page = skip // limit + 1 if limit > 0 else 1

    return {
        "items": populated_applications,
        "total": total,
        "page": current_page,
        "page_size": limit
    }


@invoice_router.get("/{application_id}", response_model=InvoiceApplicationResponse, summary="获取发票申请详情", description="获取指定发票申请的完整信息及关联业务数据")
def get_invoice_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    application = invoice_application_crud.get_by_id(db, application_id, team_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在"
        )

    return _populate_application_info(db, application, team_id)


@invoice_router.put("/{application_id}", response_model=InvoiceApplicationResponse, summary="修改发票申请", description="修改指定的发票申请信息（仅草稿状态可编辑）")
def update_invoice_application(
    application_id: int,
    application_data: InvoiceApplicationUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    application = invoice_application_crud.get_by_id(db, application_id, team_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在"
        )

    try:
        updated_application = invoice_application_crud.update(db, application, application_data)
        return _populate_application_info(db, updated_application, team_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@invoice_router.post("/{application_id}/mark-issued", response_model=InvoiceApplicationResponse, summary="标记为已开票", description="将已批准的发票申请标记为已开票状态")
def mark_invoice_issued(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:mark_issued")),
    db: Session = Depends(get_db)
):
    application = invoice_application_crud.get_by_id(db, application_id, team_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在"
        )

    try:
        issued_application = invoice_application_crud.mark_issued(db, application_id, team_id=team_id)
        return _populate_application_info(db, issued_application, team_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@invoice_router.delete("/{application_id}", response_model=MessageResponse, summary="删除发票申请", description="删除指定的发票申请（仅草稿状态可删除）")
def delete_invoice_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        success = invoice_application_crud.delete(db, application_id, team_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="发票申请不存在"
            )
        return {"message": "删除成功"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# Task 4: 发票文件下载端点（GET /invoice-applications/{application_id}/file）
# ============================================================================
# 设计要点：
# - application_id: 发票申请 ID
# - 权限：get_current_active_user（登录用户即可，发票文件无敏感信息）
# - 安全校验：FileStorageService.get_full_path 防路径穿越
# - 文件存在检查：os.path.exists
# - Content-Type 映射：按扩展名设置正确的 MIME 类型
# - Content-Disposition：attachment，文件名用 invoice_number 或 application_id
# ============================================================================


@invoice_router.get(
    "/{application_id}/file",
    summary="下载发票文件（Task 4）",
    description="""
下载已上传的发票文件。

**功能说明：**
- 仅已开票状态（ISSUED）的发票可下载
- 自动设置正确的 Content-Type（PDF/JPG/PNG/OFD）
- 文件名使用发票号码或申请 ID

**路径参数：**
- application_id: 发票申请 ID

**返回：**
- 文件内容（二进制流）
- Content-Type: application/pdf / image/jpeg / image/png / application/octet-stream
- Content-Disposition: attachment

**错误情况：**
- 发票申请不存在：404
- 未上传文件：404
- 文件不存在：404
- 文件路径非法：400
""",
)
async def download_invoice_file(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """下载发票文件"""

    application = invoice_application_crud.get_by_id(db, application_id, team_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在",
        )

    if not application.invoice_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该发票未上传文件",
        )

    # 获取文件完整路径（含安全校验）
    try:
        full_path = file_storage_service.get_full_path(application.invoice_file_path)
    except FileStorageError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件路径非法",
        )

    # 检查文件是否存在
    if not os.path.exists(full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    # 读取文件内容
    with open(full_path, "rb") as f:
        content = f.read()

    # 根据扩展名设置 Content-Type
    ext = os.path.splitext(application.invoice_file_path)[1].lower()
    content_type_map = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".ofd": "application/octet-stream",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    # 文件名：优先使用发票号码，否则用申请 ID
    filename = application.invoice_number or f"invoice_{application_id}"
    # 确保文件名有扩展名
    if not filename.endswith(ext):
        filename = f"{filename}{ext}"

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        },
    )


@invoice_router.get("/payment-plans/{payment_plan_id}/invoices", response_model=PaymentPlanInvoiceSummary, summary="获取回款计划关联发票", description="查询指定回款计划关联的所有发票申请及状态")
def get_payment_plan_invoices(
    payment_plan_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    summary = invoice_application_crud.get_payment_plan_invoice_summary(db, payment_plan_id, team_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )

    populated_invoices = [_populate_application_info(db, app, team_id) for app in summary["invoices"]]
    
    return PaymentPlanInvoiceSummary(
        payment_plan_id=summary["payment_plan_id"],
        stage_name=summary["stage_name"],
        planned_amount=summary["planned_amount"],
        total_invoiced_amount=summary["total_invoiced_amount"],
        invoice_count=summary["invoice_count"],
        invoices=populated_invoices
    )


def _populate_application_info(db: Session, application, team_id: Optional[int] = None) -> InvoiceApplicationResponse:
    """填充发票申请完整响应信息

    Changes:
    - 返回 InvoiceApplicationResponse（而非 dict）类型安全
    - 添加 invoice_file_path / invoice_number / issued_time（修复 bug）
    """
    customer_query = db.query(Customer).filter(Customer.id == application.customer_id)
    if team_id is not None:
        customer_query = customer_query.filter(Customer.team_id == team_id)
    customer = customer_query.first()

    contract_query = db.query(Contract).filter(Contract.id == application.contract_id)
    if team_id is not None:
        contract_query = contract_query.filter(Contract.team_id == team_id)
    contract = contract_query.first()

    opportunity_query = db.query(Opportunity).filter(Opportunity.id == application.opportunity_id)
    if team_id is not None:
        opportunity_query = opportunity_query.filter(Opportunity.team_id == team_id)
    opportunity = opportunity_query.first()

    payment_plan_query = db.query(PaymentPlan).filter(PaymentPlan.id == application.payment_plan_id)
    if team_id is not None:
        payment_plan_query = payment_plan_query.filter(PaymentPlan.team_id == team_id)
    payment_plan = payment_plan_query.first()

    # 查询申请人/审批人名称
    applicant_name = None
    reviewer_name = None
    if application.applicant_id:
        applicant = db.query(User).filter(User.id == int(application.applicant_id)).first()
        if applicant:
            applicant_name = applicant.name
    if application.reviewer_id:
        reviewer = db.query(User).filter(User.id == int(application.reviewer_id)).first()
        if reviewer:
            reviewer_name = reviewer.name

    return InvoiceApplicationResponse(
        id=application.id,
        application_number=application.application_number,
        customer_id=application.customer_id,
        contract_id=application.contract_id,
        opportunity_id=application.opportunity_id,
        payment_plan_id=application.payment_plan_id,
        invoice_title_id=application.invoice_title_id,
        invoice_amount=float(application.invoice_amount),
        invoice_type=application.invoice_type,
        status=application.status,
        applicant_id=application.applicant_id,
        reviewer_id=application.reviewer_id,
        review_comment=application.review_comment,
        reviewed_time=application.reviewed_time,
        payment_record_id=application.payment_record_id,
        invoice_title_type=application.invoice_title_type,
        invoice_title_text=application.invoice_title_text,
        invoice_taxpayer_id=application.invoice_taxpayer_id,
        invoice_bank_name=application.invoice_bank_name,
        invoice_bank_account=application.invoice_bank_account,
        invoice_address=application.invoice_address,
        invoice_phone=application.invoice_phone,
        created_time=application.created_time,
        last_modified_time=application.last_modified_time,

        # Bug 修复：添加三个缺失字段
        invoice_file_path=application.invoice_file_path,
        invoice_number=application.invoice_number,
        issued_time=application.issued_time,

        # 关联业务信息
        customer_name=customer.account_name if customer else None,
        contract_name=contract.contract_name if contract else None,
        opportunity_name=opportunity.opportunity_name if opportunity else None,
        payment_plan_stage_name=payment_plan.stage_name if payment_plan else None,
        invoice_title_title=application.invoice_title_text,
        applicant_name=applicant_name,
        reviewer_name=reviewer_name,
    )
