"""
发票开放接口路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.openapi.deps import require_api_permission, verify_api_key
from app.crud.invoice import invoice_title_crud, invoice_application_crud
from app.crud.payment import payment_plan_crud
from app.crud.contract import contract_crud
from app.models.api_key import ApiKey
from app.models.invoice import InvoiceApplicationStatus, InvoiceType
from app.schemas.openapi.common import OpenApiResponse, success_response, paginated_response
from app.schemas.openapi.invoice import (
    OpenApiInvoiceTitleCreate, OpenApiInvoiceApplicationCreate, OpenApiInvoiceMarkIssued,
    OpenApiInvoiceTitleResponse, OpenApiInvoiceApplicationResponse,
    OpenApiInvoiceApplicationCreateResponse, OpenApiInvoiceApplicationStatusResponse,
    INVOICE_TYPE_NAMES, INVOICE_APPLICATION_STATUS_NAMES
)
from app.services.data_masker import data_masker

router = APIRouter()


@router.post("/invoice-titles", summary="添加发票抬头", description="为客户添加发票抬头")
async def create_invoice_title(
    data: OpenApiInvoiceTitleCreate = Body(..., description="发票抬头数据"),
    api_key: ApiKey = Depends(require_api_permission("invoice:create")),
    db: Session = Depends(get_db)
):
    """添加发票抬头接口"""
    # 创建发票抬头
    title = invoice_title_crud.create(
        db=db,
        customer_id=data.customer_id,
        title_name=data.title_name,
        tax_number=data.tax_number,
        bank_name=data.bank_name,
        bank_account=data.bank_account,
        address=data.address,
        phone=data.phone,
        title_type="COMPANY"  # 默认企业抬头
    )

    if data.is_default:
        invoice_title_crud.set_default(db, title.id)

    return success_response({"title_id": title.id}, message="发票抬头添加成功")


@router.post("/invoice-applications", summary="创建发票申请", description="基于回款计划创建发票申请")
async def create_invoice_application(
    data: OpenApiInvoiceApplicationCreate = Body(..., description="发票申请数据"),
    api_key: ApiKey = Depends(require_api_permission("invoice:create")),
    db: Session = Depends(get_db)
):
    """创建发票申请接口"""
    # 校验回款计划
    plan = payment_plan_crud.get_by_id(db, data.payment_plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )

    # 校验发票抬头
    title = invoice_title_crud.get_by_id(db, data.invoice_title_id)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票抬头不存在"
        )

    # 创建发票申请
    application = invoice_application_crud.create(
        db=db,
        payment_plan_id=data.payment_plan_id,
        payment_record_id=None,
        invoice_title_id=data.invoice_title_id,
        invoice_amount=data.invoice_amount,
        invoice_type=InvoiceType(data.invoice_type.value),
        applicant_id="openapi_system",
        applicant_name="开放接口"
    )

    response = OpenApiInvoiceApplicationCreateResponse(
        application_id=application.id,
        status="DRAFT"
    )

    return success_response(response, message="发票申请创建成功")


@router.get("/invoice-applications", summary="查询发票申请列表", description="查询发票申请列表")
async def get_invoice_applications(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(None, description="申请状态筛选"),
    api_key: ApiKey = Depends(require_api_permission("invoice:list")),
    db: Session = Depends(get_db)
):
    """查询发票申请列表接口"""
    skip = (page - 1) * page_size

    # get_multi 可能返回 list 或 (list, total)，需要处理
    result = invoice_application_crud.get_multi(db, skip=skip, limit=page_size)
    if isinstance(result, tuple):
        applications, total = result
    else:
        applications = result
        total = len(applications)

    items = []
    for app in applications:
        # 获取相关信息
        plan = payment_plan_crud.get_by_id(db, app.payment_plan_id) if app.payment_plan_id else None
        contract = plan.contract if plan else None
        customer = contract.customer if contract else None

        items.append(OpenApiInvoiceApplicationResponse(
            application_id=app.id,
            payment_plan_id=app.payment_plan_id or 0,
            customer_id=customer.id if customer else 0,
            customer_name=customer.account_name if customer else "",
            contract_id=contract.id if contract else 0,
            contract_name=contract.contract_name if contract else "",
            invoice_title_name=app.invoice_title.title_name if app.invoice_title else "",
            tax_number=app.invoice_title_snapshot.get("tax_number", "") if app.invoice_title_snapshot else "",
            invoice_amount=float(app.invoice_amount) if app.invoice_amount else 0,
            invoice_type=app.invoice_type.name if app.invoice_type else "VAT_SPECIAL",
            invoice_type_name=INVOICE_TYPE_NAMES.get(app.invoice_type, "增值税专用发票") if app.invoice_type else "增值税专用发票",
            status=app.status or "DRAFT",
            status_name=INVOICE_APPLICATION_STATUS_NAMES.get(app.status, "草稿") if app.status else "草稿",
            invoice_no=app.invoice_no,
            issue_date=app.issue_date,
            create_time=app.created_time
        ))

    return paginated_response(items, total, page, page_size)


@router.post("/invoice-applications/{application_id}/submit", summary="提交发票申请审批", description="提交发票申请进入审批流程")
async def submit_invoice_application(
    application_id: int = Path(..., description="发票申请ID"),
    api_key: ApiKey = Depends(require_api_permission("invoice:create")),
    db: Session = Depends(get_db)
):
    """提交发票申请审批接口"""
    application = invoice_application_crud.get_by_id(db, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在"
        )

    if application.status != InvoiceApplicationStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有草稿状态的申请可以提交"
        )

    # 更新状态为待审批
    application.status = InvoiceApplicationStatus.PENDING_REVIEW
    db.commit()

    return success_response({"application_id": application.id, "status": "PENDING_REVIEW"}, message="发票申请已提交审批")


@router.post("/invoice-applications/{application_id}/mark-issued", summary="标记发票已开具", description="标记发票已开具（财务系统调用）")
async def mark_invoice_issued(
    application_id: int = Path(..., description="发票申请ID"),
    data: OpenApiInvoiceMarkIssued = Body(..., description="发票开具信息"),
    api_key: ApiKey = Depends(require_api_permission("invoice:approve")),
    db: Session = Depends(get_db)
):
    """标记发票已开具接口"""
    application = invoice_application_crud.get_by_id(db, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在"
        )

    if application.status not in [InvoiceApplicationStatus.APPROVED, InvoiceApplicationStatus.PENDING_REVIEW]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有已批准或待审批的申请可以标记已开具"
        )

    # 更新状态为已开票
    application.status = InvoiceApplicationStatus.ISSUED
    application.invoice_no = data.invoice_no
    application.issue_date = data.issue_date
    db.commit()

    return success_response({"application_id": application.id, "status": "ISSUED"}, message="发票已标记为开具")