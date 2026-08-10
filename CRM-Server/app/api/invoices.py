import logging
import os
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.core.database import get_db
from app.core.deps import (
    check_customer_edit_permission,
    check_customer_view_permission,
    check_invoice_edit_permission,
    check_invoice_view_permission,
    check_payment_view_permission,
    get_current_active_user,
    get_current_user_team,
    require_permission,
)
from app.crud.approval import approval_crud
from app.crud.invoice import invoice_application_crud, invoice_red_offset_crud, invoice_reissue_application_crud, invoice_title_crud
from app.models.approval import ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import InvoiceApplicationStatus
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan
from app.models.user import User
from app.schemas.invoice import (
    InvoiceApplicationCreate,
    InvoiceApplicationListResponse,
    InvoiceApplicationResponse,
    InvoiceApplicationUpdate,
    InvoiceReissueApplicationCreate,
    InvoiceReissueApplicationResponse,
    InvoiceReissueApplicationUpdate,
    InvoiceRedOffsetResponse,
    InvoiceTitleCreate,
    InvoiceTitleListResponse,
    InvoiceTitleResponse,
    InvoiceTitleUpdate,
    MessageResponse,
    PaymentPlanInvoiceSummary,
)
from app.services.approval_adapter import get_adapter, get_approval_card_fields
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeRefreshInput,
    CustomerBusinessObjectChangeType,
    customer_business_object_intelligence_service,
)
from app.services.feishu_notification import feishu_notification_service
from app.services.file_storage import FileStorageError, file_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoice-titles", tags=["开票抬头管理"])


def _invoice_title_response(db: Session, title, team_id: Optional[int] = None) -> InvoiceTitleResponse:
    customer_query = db.query(Customer).filter(Customer.id == title.customer_id)
    if team_id is not None:
        customer_query = customer_query.filter(Customer.team_id == team_id)
    customer = customer_query.first()
    return InvoiceTitleResponse(**{
        "id": title.id,
        "customer_id": customer.public_id if customer else None,
        "title_type": title.title_type,
        "title": title.title,
        "taxpayer_id": title.taxpayer_id,
        "bank_name": title.bank_name,
        "bank_account": title.bank_account,
        "address": title.address,
        "phone": title.phone,
        "is_default": title.is_default,
        "created_time": title.created_time,
        "last_modified_time": title.last_modified_time,
    })


def _build_invoice_title_intelligence_change(
    title,
    *,
    change_type: Literal["created", "updated", "deleted"],
    actor_id: str | None,
) -> CustomerBusinessObjectChangeRefreshInput:
    change = customer_business_object_intelligence_service.build_change(
        None,
        source_type="invoice_title",
        business_object=title,
        change_type=change_type,
        actor_id=actor_id,
    )
    if change is None:
        raise ValueError("开票抬头缺少客户智能刷新所需字段")
    return change


def _enqueue_invoice_business_object_intelligence_refresh(
    db: Session,
    change: CustomerBusinessObjectChangeRefreshInput | None,
) -> None:
    if change is None:
        return
    customer_business_object_intelligence_service.enqueue_change_refresh(db, change)


def _build_invoice_application_intelligence_change(
    application,
    *,
    change_type: CustomerBusinessObjectChangeType,
    actor_id: str | None,
) -> CustomerBusinessObjectChangeRefreshInput:
    change = customer_business_object_intelligence_service.build_change(
        None,
        source_type="invoice_application",
        business_object=application,
        change_type=change_type,
        actor_id=actor_id,
    )
    if change is None:
        raise ValueError("发票申请缺少客户智能刷新所需字段")
    return change


def _enqueue_invoice_application_intelligence_refresh(
    db: Session,
    change: CustomerBusinessObjectChangeRefreshInput,
) -> None:
    _enqueue_invoice_business_object_intelligence_refresh(db, change)


@router.post("", response_model=InvoiceTitleResponse, summary="添加开票抬头", description="为指定客户添加开票抬头信息")
def create_invoice_title(
    customer_id: str = Query(..., description="客户对外ID"),
    title_data: InvoiceTitleCreate = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:title:create")),
    db: Session = Depends(get_db)
):
    customer = check_customer_edit_permission(customer_id, team_id, current_user, db)

    existing_title = invoice_title_crud.get_by_taxpayer_id(db, customer.id, title_data.taxpayer_id, team_id)
    if existing_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该纳税人识别号已存在"
        )

    title = invoice_title_crud.create(db, customer.id, title_data, team_id)
    _enqueue_invoice_business_object_intelligence_refresh(
        db,
        _build_invoice_title_intelligence_change(
            title,
            change_type="created",
            actor_id=str(current_user.id),
        ),
    )
    return _invoice_title_response(db, title, team_id)


@router.get("", response_model=InvoiceTitleListResponse, summary="查询开票抬头列表", description="获取指定客户的所有开票抬头")
def list_invoice_titles(
    customer_id: str = Query(..., description="客户对外ID"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    titles = invoice_title_crud.get_by_customer_id(db, customer.id, team_id)
    return {"invoice_titles": [_invoice_title_response(db, title, team_id) for title in titles]}


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
    check_customer_view_permission(title.customer_id, team_id, current_user, db)
    return _invoice_title_response(db, title, team_id)


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
    check_customer_edit_permission(title.customer_id, team_id, current_user, db)

    updated_title = invoice_title_crud.update(db, title, title_data)
    _enqueue_invoice_business_object_intelligence_refresh(
        db,
        _build_invoice_title_intelligence_change(
            updated_title,
            change_type="updated",
            actor_id=str(current_user.id),
        ),
    )
    return _invoice_title_response(db, updated_title, team_id)


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
    check_customer_edit_permission(title.customer_id, team_id, current_user, db)

    updated_title = invoice_title_crud.set_default(db, title.customer_id, title_id)
    if not updated_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="设置默认抬头失败"
        )
    _enqueue_invoice_business_object_intelligence_refresh(
        db,
        _build_invoice_title_intelligence_change(
            updated_title,
            change_type="updated",
            actor_id=str(current_user.id),
        ),
    )
    return _invoice_title_response(db, updated_title, team_id)


@router.delete("/{title_id}", response_model=MessageResponse, summary="删除开票抬头", description="删除指定的开票抬头")
def delete_invoice_title(
    title_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:title:delete")),
    db: Session = Depends(get_db)
):
    title = invoice_title_crud.get_by_id(db, title_id, team_id)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="开票抬头不存在"
        )
    check_customer_edit_permission(title.customer_id, team_id, current_user, db)

    change = _build_invoice_title_intelligence_change(
        title,
        change_type="deleted",
        actor_id=str(current_user.id),
    )
    success = invoice_title_crud.delete(db, title_id, team_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="删除开票抬头失败"
        )
    _enqueue_invoice_business_object_intelligence_refresh(db, change)
    return {"message": "删除成功"}


invoice_router = APIRouter(prefix="/invoice-applications", tags=["发票申请管理"])


@invoice_router.post("", response_model=InvoiceApplicationResponse, summary="创建发票申请", description="创建新的发票申请，自动关联业务上下文（客户、合同、商机、回款计划）")
def create_invoice_application(
    application_data: InvoiceApplicationCreate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:create")),
    db: Session = Depends(get_db)
):
    try:
        application = invoice_application_crud.create(
            db,
            application_data,
            str(current_user.id),
            team_id
        )
        _enqueue_invoice_application_intelligence_refresh(
            db,
            _build_invoice_application_intelligence_change(
                application,
                change_type="created",
                actor_id=str(current_user.id),
            ),
        )
        return _populate_application_info(db, application, team_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@invoice_router.get("", response_model=InvoiceApplicationListResponse, summary="查询发票申请列表", description="支持按客户、合同、状态等多条件筛选发票申请")
def list_invoice_applications(
    customer_id: Optional[str] = Query(None, description="客户对外ID"),
    contract_id: Optional[int] = Query(None, description="合同ID"),
    payment_plan_id: Optional[int] = Query(None, description="回款计划ID"),
    application_status: Optional[str] = Query(None, alias="status", description="申请状态，多个值用逗号分隔"),
    status_exclude: Optional[str] = Query(None, description="排除的申请状态，多个值用逗号分隔"),
    invoice_type: Optional[str] = Query(None, description="发票类型，多个值用逗号分隔"),
    invoice_type_exclude: Optional[str] = Query(None, description="排除的发票类型，多个值用逗号分隔"),
    invoice_effective_status: Optional[str] = Query(None, description="发票有效状态，多个值用逗号分隔：ACTIVE/REISSUE_PENDING/RED_OFFSET/REISSUED"),
    applicant_id: Optional[str] = Query(None, description="申请人ID"),
    keyword: Optional[str] = Query(None, description="关键词，支持申请编号、客户、合同、抬头、税号、发票号码"),
    created_time_start: Optional[date] = Query(None, description="创建时间起始"),
    created_time_end: Optional[date] = Query(None, description="创建时间结束"),
    order_by: Optional[str] = Query(None, description="排序字段"),
    order_dir: Optional[str] = Query(None, description="排序方向 asc/desc"),
    page: Optional[int] = Query(None, ge=1, description="页码（兼容前端 page/page_size）"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="每页记录数（兼容前端 page/page_size）"),
    me: bool = Query(False, description="是否只查询当前用户申请的数据"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    查询发票申请列表（添加权限隔离）

    权限逻辑：
    - invoice:view:all → 可查看所有发票申请
    - invoice:view:own → 只能查看自己申请的发票
    - 都没有 → 403 Forbidden
    """
    from app.crud.permission import permission_crud

    # 权限检查
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    has_view_all = "invoice:view:all" in permission_codes
    has_view_own = "invoice:view:own" in permission_codes

    if not has_view_all and not has_view_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有查看发票申请的权限"
        )

    # 数据所有权隔离
    current_user_id = None
    if me or (has_view_own and not has_view_all):
        # 如果只有 view:own 权限，或者用户明确选择只看自己的数据
        current_user_id = str(current_user.id)

    effective_limit = page_size if page_size is not None else limit
    effective_skip = (page - 1) * effective_limit if page is not None else skip

    internal_customer_id = None
    if customer_id:
        customer = check_customer_view_permission(customer_id, team_id, current_user, db)
        internal_customer_id = customer.id

    applications, total = invoice_application_crud.list_applications(
        db,
        team_id=team_id,
        skip=effective_skip,
        limit=effective_limit,
        customer_id=internal_customer_id,
        contract_id=contract_id,
        payment_plan_id=payment_plan_id,
        status=application_status,
        status_exclude=status_exclude,
        invoice_type=invoice_type,
        invoice_type_exclude=invoice_type_exclude,
        invoice_effective_status=invoice_effective_status,
        applicant_id=applicant_id,
        current_user_id=current_user_id,
        keyword=keyword,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        order_by=order_by,
        order_dir=order_dir,
    )

    populated_applications = [_populate_application_info(db, app, team_id) for app in applications]

    # 计算页码（skip/limit + 1）
    current_page = page if page is not None else (effective_skip // effective_limit + 1 if effective_limit > 0 else 1)

    return {
        "items": populated_applications,
        "total": total,
        "page": current_page,
        "page_size": effective_limit
    }


@invoice_router.post(
    "/{application_id}/reissues",
    response_model=InvoiceReissueApplicationResponse,
    summary="创建发票重开申请",
    description="对已开票的发票申请创建重开申请，原发票不被替换",
)
def create_invoice_reissue_application(
    application_id: int,
    reissue_data: InvoiceReissueApplicationCreate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice_reissue:create")),
    db: Session = Depends(get_db),
):
    original_invoice = check_invoice_view_permission(application_id, team_id, current_user, db)
    try:
        reissue = invoice_reissue_application_crud.create(
            db,
            original_invoice=original_invoice,
            obj_in=reissue_data,
            applicant_id=str(current_user.id),
            team_id=team_id,
        )
        return _populate_reissue_application_info(db, reissue)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@invoice_router.put(
    "/reissues/{reissue_id}",
    response_model=InvoiceReissueApplicationResponse,
    summary="修改发票重开申请",
    description="仅草稿或已拒绝状态可修改",
)
def update_invoice_reissue_application(
    reissue_id: int,
    reissue_data: InvoiceReissueApplicationUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    reissue = invoice_reissue_application_crud.get_by_id(db, reissue_id, team_id)
    if not reissue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票重开申请不存在")
    if reissue.applicant_id != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能编辑自己申请的发票重开申请")

    try:
        updated = invoice_reissue_application_crud.update(db, reissue, reissue_data)
        return _populate_reissue_application_info(db, updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@invoice_router.post(
    "/reissues/{reissue_id}/complete",
    response_model=InvoiceReissueApplicationResponse,
    summary="完成发票重开",
    description="财务上传红字发票和新蓝字发票后完成重开",
)
async def complete_invoice_reissue(
    reissue_id: int,
    red_file: UploadFile = File(..., description="红字发票文件"),
    new_file: UploadFile = File(..., description="新蓝字发票文件"),
    red_invoice_number: Optional[str] = Form(None, description="红字发票号码"),
    new_invoice_number: Optional[str] = Form(None, description="新蓝字发票号码"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:mark_issued")),
    db: Session = Depends(get_db),
):
    reissue = invoice_reissue_application_crud.get_by_id(db, reissue_id, team_id)
    if not reissue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票重开申请不存在")

    red_number = red_invoice_number.strip() if red_invoice_number else None
    new_number = new_invoice_number.strip() if new_invoice_number else None

    try:
        red_file_path = file_storage_service.save_invoice_file(
            team_id=team_id,
            invoice_id=reissue_id,
            filename=red_file.filename or "",
            content=await red_file.read(),
        )
        new_file_path = file_storage_service.save_invoice_file(
            team_id=team_id,
            invoice_id=reissue_id,
            filename=new_file.filename or "",
            content=await new_file.read(),
        )
    except FileStorageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        completed = invoice_reissue_application_crud.complete(
            db,
            reissue_id,
            team_id,
            red_invoice_file_path=red_file_path,
            red_invoice_number=red_number,
            new_invoice_file_path=new_file_path,
            new_invoice_number=new_number,
        )
        if not completed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票重开申请不存在")
        return _populate_reissue_application_info(db, completed)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@invoice_router.get(
    "/reissues/{reissue_id}/{file_kind}-file",
    summary="下载发票重开相关文件",
    description="下载红字发票或新蓝字发票文件，file_kind 为 red 或 new",
)
async def download_invoice_reissue_file(
    reissue_id: int,
    file_kind: Literal["red", "new"],
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    reissue = invoice_reissue_application_crud.get_by_id(db, reissue_id, team_id)
    if not reissue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票重开申请不存在")

    original = reissue.original_invoice_application
    if original is None:
        original = invoice_application_crud.get_by_id(db, reissue.original_invoice_application_id, team_id)
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原发票申请不存在")
    check_invoice_view_permission(original.id, team_id, current_user, db)

    file_path = reissue.red_invoice_file_path if file_kind == "red" else reissue.new_invoice_file_path
    invoice_number = reissue.red_invoice_number if file_kind == "red" else reissue.new_invoice_number
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该发票文件未上传")

    return _download_invoice_path(file_path, invoice_number or f"invoice-reissue-{reissue_id}-{file_kind}")


@invoice_router.get(
    "/red-offsets/{red_offset_id}/file",
    summary="下载发票冲红文件",
    description="下载手动冲红或重开流程生成的红字发票文件",
)
async def download_invoice_red_offset_file(
    red_offset_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    red_offset = invoice_red_offset_crud.get_by_id(db, red_offset_id, team_id)
    if not red_offset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票冲红记录不存在")

    check_invoice_view_permission(red_offset.invoice_application_id, team_id, current_user, db)
    filename_base = f"red-offset-{red_offset.red_invoice_number or red_offset_id}"
    return _download_invoice_path(red_offset.red_invoice_file_path, filename_base)


@invoice_router.get("/{application_id}", response_model=InvoiceApplicationResponse, summary="获取发票申请详情", description="获取指定发票申请的完整信息及关联业务数据")
def get_invoice_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    application = check_invoice_view_permission(application_id, team_id, current_user, db)

    return _populate_application_info(db, application, team_id)


@invoice_router.put("/{application_id}", response_model=InvoiceApplicationResponse, summary="修改发票申请", description="修改指定的发票申请信息（仅草稿状态可编辑）")
def update_invoice_application(
    application_id: int,
    application_data: InvoiceApplicationUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    application = check_invoice_edit_permission(application_id, team_id, current_user, db)

    try:
        updated_application = invoice_application_crud.update(db, application, application_data)
        _enqueue_invoice_application_intelligence_refresh(
            db,
            _build_invoice_application_intelligence_change(
                updated_application,
                change_type="updated",
                actor_id=str(current_user.id),
            ),
        )
        return _populate_application_info(db, updated_application, team_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@invoice_router.post(
    "/{application_id}/mark-issued",
    response_model=InvoiceApplicationResponse,
    summary="标记为已开票",
    description="审批通过后执行开票业务动作，可选上传发票文件和填写发票号码",
)
async def mark_invoice_issued(
    application_id: int,
    file: Optional[UploadFile] = File(None, description="发票文件（PDF/JPG/PNG/OFD，可选）"),
    invoice_number: Optional[str] = Form(None, description="发票号码（可选）"),
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

    approval = approval_crud.get_by_entity(db, BusinessType.INVOICE, application_id, team_id)
    if not approval or approval.status != ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="发票未通过审批，不可开票"
        )

    if application.status != InvoiceApplicationStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"发票申请状态为 {application.status}，不可开票"
        )

    invoice_file_path = None
    if file is not None:
        try:
            content = await file.read()
            invoice_file_path = file_storage_service.save_invoice_file(
                team_id=team_id,
                invoice_id=application_id,
                filename=file.filename or "",
                content=content,
            )
        except FileStorageError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    normalized_invoice_number = invoice_number.strip() if invoice_number and invoice_number.strip() else None

    try:
        issued_application = invoice_application_crud.mark_issued(
            db,
            application_id,
            team_id=team_id,
            invoice_file_path=invoice_file_path,
            invoice_number=normalized_invoice_number,
        )
        _enqueue_invoice_application_intelligence_refresh(
            db,
            _build_invoice_application_intelligence_change(
                issued_application,
                change_type="updated",
                actor_id=str(current_user.id),
            ),
        )
        try:
            await feishu_notification_service.notify_approval_issued(
                db=db,
                team_id=team_id,
                user_id=int(approval.submitter_id),
                entity_type=BusinessType.INVOICE,
                entity_name=get_adapter(BusinessType.INVOICE).get_name(issued_application),
                detail_fields=get_approval_card_fields(db, BusinessType.INVOICE, issued_application),
                button_path="/invoices",
            )
        except Exception as notify_error:
            logger.error(
                f"[Invoice] Issue notification failed: application_id={application_id}, error={str(notify_error)}"
            )
        return _populate_application_info(db, issued_application, team_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@invoice_router.post(
    "/{application_id}/red-offset",
    response_model=InvoiceApplicationResponse,
    summary="冲红发票",
    description="财务上传红字发票后，将已开票发票标记为已冲红；不进入审批流程",
)
async def red_offset_invoice(
    application_id: int,
    file: UploadFile = File(..., description="红字发票文件"),
    red_invoice_number: Optional[str] = Form(None, description="红字发票号码"),
    reason: Optional[str] = Form(None, description="冲红原因"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:mark_issued")),
    db: Session = Depends(get_db),
):
    application = invoice_application_crud.get_by_id(db, application_id, team_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票申请不存在")

    try:
        invoice_red_offset_crud.assert_can_create_manual(db, application, team_id=team_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        red_file_path = file_storage_service.save_invoice_file(
            team_id=team_id,
            invoice_id=application_id,
            filename=file.filename or "",
            content=await file.read(),
        )
    except FileStorageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    red_number = red_invoice_number.strip() if red_invoice_number and red_invoice_number.strip() else None
    normalized_reason = reason.strip() if reason and reason.strip() else None

    try:
        invoice_red_offset_crud.create_manual(
            db,
            application,
            red_invoice_file_path=red_file_path,
            red_invoice_number=red_number,
            reason=normalized_reason,
            created_by=str(current_user.id),
            team_id=team_id,
        )
        db.refresh(application)
        return _populate_application_info(db, application, team_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@invoice_router.delete("/{application_id}", response_model=MessageResponse, summary="删除发票申请", description="删除指定的发票申请（审批中或审批通过后不可删除）")
def delete_invoice_application(
    application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        application = check_invoice_edit_permission(application_id, team_id, current_user, db)
        change = _build_invoice_application_intelligence_change(
            application,
            change_type="deleted",
            actor_id=str(current_user.id),
        )
        success = invoice_application_crud.delete(db, application_id, team_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="发票申请不存在"
            )
        _enqueue_invoice_application_intelligence_refresh(db, change)
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

    application = check_invoice_view_permission(application_id, team_id, current_user, db)

    if not application.invoice_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该发票未上传文件",
        )

    return _download_invoice_path(application.invoice_file_path, application.invoice_number or f"invoice_{application_id}")


@invoice_router.get("/payment-plans/{payment_plan_id}/invoices", response_model=PaymentPlanInvoiceSummary, summary="获取回款计划关联发票", description="查询指定回款计划关联的所有发票申请及状态")
def get_payment_plan_invoices(
    payment_plan_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    check_payment_view_permission(payment_plan_id, team_id, current_user, db)

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

    reissues = invoice_reissue_application_crud.get_by_original_invoice(db, application.id, team_id)
    red_offsets = invoice_red_offset_crud.get_by_invoice(db, application.id, team_id)
    reissue_status = "NONE"
    completed_reissues = [
        reissue
        for reissue in reissues
        if reissue.status == "COMPLETED" and reissue.new_invoice_file_path
    ]
    latest_completed_reissue = max(
        completed_reissues,
        key=lambda reissue: (reissue.completed_time or reissue.last_modified_time or reissue.created_time, reissue.id),
        default=None,
    )
    if latest_completed_reissue is not None:
        reissue_status = "REISSUED"
    elif any(reissue.status in {"DRAFT", "PENDING_REVIEW", "APPROVED"} for reissue in reissues):
        reissue_status = "REISSUE_PENDING"

    latest_red_offset = max(
        red_offsets,
        key=lambda red_offset: (red_offset.red_offset_time or red_offset.last_modified_time or red_offset.created_time, red_offset.id),
        default=None,
    )

    if latest_completed_reissue is not None:
        invoice_effective_status = "REISSUED"
        current_invoice_file_kind = "reissue_new"
        current_invoice_file_path = latest_completed_reissue.new_invoice_file_path
        current_invoice_number = latest_completed_reissue.new_invoice_number
        current_reissue_id = latest_completed_reissue.id
    elif latest_red_offset is not None:
        invoice_effective_status = "RED_OFFSET"
        current_invoice_file_kind = None
        current_invoice_file_path = None
        current_invoice_number = None
        current_reissue_id = None
    else:
        invoice_effective_status = "REISSUE_PENDING" if reissue_status == "REISSUE_PENDING" else "ACTIVE"
        current_invoice_file_kind = "original" if application.invoice_file_path else None
        current_invoice_file_path = application.invoice_file_path
        current_invoice_number = application.invoice_number
        current_reissue_id = None

    return InvoiceApplicationResponse(
        id=application.id,
        application_number=application.application_number,
        customer_id=customer.public_id if customer else None,
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
        reissue_status=reissue_status,
        invoice_effective_status=invoice_effective_status,
        current_invoice_file_kind=current_invoice_file_kind,
        current_invoice_file_path=current_invoice_file_path,
        current_invoice_number=current_invoice_number,
        current_reissue_id=current_reissue_id,
        red_offsets=[_populate_red_offset_info(db, red_offset) for red_offset in red_offsets],
        reissue_applications=[_populate_reissue_application_info(db, reissue) for reissue in reissues],
    )


def _populate_red_offset_info(db: Session, red_offset) -> InvoiceRedOffsetResponse:
    created_by_name = None
    if red_offset.created_by and str(red_offset.created_by).isdigit():
        creator = db.query(User).filter(User.id == int(red_offset.created_by)).first()
        if creator:
            created_by_name = creator.name

    return InvoiceRedOffsetResponse(
        id=red_offset.id,
        invoice_application_id=red_offset.invoice_application_id,
        source_type=red_offset.source_type,
        reissue_application_id=red_offset.reissue_application_id,
        red_invoice_file_path=red_offset.red_invoice_file_path,
        red_invoice_number=red_offset.red_invoice_number,
        reason=red_offset.reason,
        created_by=red_offset.created_by,
        created_by_name=created_by_name,
        red_offset_time=red_offset.red_offset_time,
        created_time=red_offset.created_time,
        last_modified_time=red_offset.last_modified_time,
    )


def _populate_reissue_application_info(db: Session, reissue) -> InvoiceReissueApplicationResponse:
    applicant_name = None
    if reissue.applicant_id:
        applicant = db.query(User).filter(User.id == int(reissue.applicant_id)).first()
        if applicant:
            applicant_name = applicant.name

    return InvoiceReissueApplicationResponse(
        id=reissue.id,
        application_number=reissue.application_number,
        original_invoice_application_id=reissue.original_invoice_application_id,
        applicant_id=reissue.applicant_id,
        applicant_name=applicant_name,
        reason=reissue.reason,
        status=reissue.status,
        approval_phase=reissue.approval_phase,
        invoice_title_type=reissue.invoice_title_type,
        invoice_title_text=reissue.invoice_title_text,
        invoice_taxpayer_id=reissue.invoice_taxpayer_id,
        invoice_bank_name=reissue.invoice_bank_name,
        invoice_bank_account=reissue.invoice_bank_account,
        invoice_address=reissue.invoice_address,
        invoice_phone=reissue.invoice_phone,
        invoice_amount=reissue.invoice_amount,
        invoice_type=reissue.invoice_type,
        red_invoice_file_path=reissue.red_invoice_file_path,
        red_invoice_number=reissue.red_invoice_number,
        red_issued_time=reissue.red_issued_time,
        new_invoice_file_path=reissue.new_invoice_file_path,
        new_invoice_number=reissue.new_invoice_number,
        new_issued_time=reissue.new_issued_time,
        completed_time=reissue.completed_time,
        created_time=reissue.created_time,
        last_modified_time=reissue.last_modified_time,
    )


def _download_invoice_path(file_path: str, filename_base: str) -> Response:
    try:
        full_path = file_storage_service.get_full_path(file_path)
    except FileStorageError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件路径非法")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    with open(full_path, "rb") as f:
        content = f.read()

    ext = os.path.splitext(file_path)[1].lower()
    content_type_map = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".ofd": "application/octet-stream",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")
    filename = filename_base
    if not filename.endswith(ext):
        filename = f"{filename}{ext}"

    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )
