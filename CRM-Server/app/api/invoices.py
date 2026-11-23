import logging
import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import date
from typing import Literal, TypedDict, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.core.database import SessionLocal, get_db
from app.core.deps import (
    check_customer_edit_permission,
    check_customer_view_permission,
    check_invoice_edit_permission,
    check_invoice_view_permission,
    check_invoice_write_scope,
    check_payment_view_permission,
    get_current_active_user,
    get_current_user_team,
    get_viewable_customer_ids,
    require_permission,
)
from app.core.list_export import (
    INVOICES_LIST_EXPORT_CATALOG,
    create_list_export_file,
    iter_batches,
    list_export_file_response,
    run_list_export_or_400,
)
from app.core.list_query import optional_request_list_query, run_or_400
from app.crud.approval import approval_crud
from app.crud.invoice import (
    invoice_application_crud,
    invoice_red_offset_crud,
    invoice_reissue_application_crud,
    invoice_title_crud,
)
from app.models.approval import ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import (
    InvoiceApplication,
    InvoiceApplicationStatus,
    InvoiceRedOffset,
    InvoiceReissueApplication,
    InvoiceTitle,
)
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan
from app.models.user import User
from app.schemas.invoice import (
    InvoiceApplicationCreate,
    InvoiceApplicationListResponse,
    InvoiceApplicationResponse,
    InvoiceApplicationUpdate,
    InvoiceRedOffsetResponse,
    InvoiceReissueApplicationCreate,
    InvoiceReissueApplicationResponse,
    InvoiceReissueApplicationUpdate,
    InvoiceTitleCreate,
    InvoiceTitleListResponse,
    InvoiceTitleResponse,
    InvoiceTitleUpdate,
    MessageResponse,
    PaymentPlanInvoiceSummary,
)
from app.schemas.list_export import InvoiceListExportRequest
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeRefreshInput,
    CustomerBusinessObjectChangeType,
    customer_business_object_intelligence_service,
)
from app.services.file_storage import FileStorageError, file_storage_service
from app.services.outbound_notification_job_service import outbound_notification_job_service

logger = logging.getLogger(__name__)

_TEAM = Depends(get_current_user_team)
_ACTIVE_USER = Depends(get_current_active_user)
_DB = Depends(get_db)
_CREATE_TITLE_USER = Depends(require_permission("invoice:title:create"))
_EDIT_TITLE_USER = Depends(require_permission("invoice:title:edit"))
_SET_DEFAULT_TITLE_USER = Depends(require_permission("invoice:title:set_default"))
_DELETE_TITLE_USER = Depends(require_permission("invoice:title:delete"))
_CREATE_INVOICE_USER = Depends(require_permission("invoice:create"))
_CREATE_REISSUE_USER = Depends(require_permission("invoice_reissue:create"))
_COMPLETE_REISSUE_USER = Depends(require_permission("invoice:mark_issued"))
_MARK_ISSUED_USER = Depends(require_permission("invoice:mark_issued"))
_RED_OFFSET_USER = Depends(require_permission("invoice:mark_issued"))
_CREATED_TIME_START = Query(None, description="创建时间起始")
_CREATED_TIME_END = Query(None, description="创建时间结束")
_COMPLETE_RED_FILE = File(..., description="红字发票文件")
_COMPLETE_NEW_FILE = File(..., description="新蓝字发票文件")
_ISSUED_FILE = File(None, description="发票文件\uff08PDF/JPG/PNG/OFD\uff0c可选\uff09")
_RED_OFFSET_FILE = File(..., description="红字发票文件")
# Keep the optional default without advertising a nullable body in OpenAPI.
_EMPTY_TITLE_DATA = cast("InvoiceTitleCreate", None)


class _InvoiceTitleListPayload(TypedDict):
    invoice_titles: list[InvoiceTitleResponse]


router = APIRouter(prefix="/invoice-titles", tags=["开票抬头管理"])


def _invoice_title_response(
    db: Session, title: InvoiceTitle, team_id: int | None = None
) -> InvoiceTitleResponse:
    customer_query = db.query(Customer).filter(Customer.id == title.customer_id)
    if team_id is not None:
        customer_query = customer_query.filter(Customer.team_id == team_id)
    customer = customer_query.first()
    return InvoiceTitleResponse.model_validate({
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
    title: InvoiceTitle,
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
    _db: Session,
    change: CustomerBusinessObjectChangeRefreshInput | None,
) -> None:
    if change is None:
        return
    customer_business_object_intelligence_service.enqueue_change_refresh_after_commit(change)


def _build_invoice_application_intelligence_change(
    application: InvoiceApplication | None,
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
    title_data: InvoiceTitleCreate = _EMPTY_TITLE_DATA,
    team_id: int = _TEAM,
    current_user: User = _CREATE_TITLE_USER,
    db: Session = _DB
) -> InvoiceTitleResponse:
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


@router.get(
    "",
    response_model=InvoiceTitleListResponse,
    summary="查询开票抬头列表",
    description="获取指定客户的所有开票抬头",
)
def list_invoice_titles(
    customer_id: str = Query(..., description="客户对外ID"),
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB
) -> _InvoiceTitleListPayload:
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    titles = invoice_title_crud.get_by_customer_id(db, customer.id, team_id)
    return {"invoice_titles": [_invoice_title_response(db, title, team_id) for title in titles]}


@router.get(
    "/{title_id}",
    response_model=InvoiceTitleResponse,
    summary="获取开票抬头详情",
    description="获取指定开票抬头的详细信息",
)
def get_invoice_title(
    title_id: int,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB
) -> InvoiceTitleResponse:
    title = invoice_title_crud.get_by_id(db, title_id, team_id)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="开票抬头不存在"
        )
    check_customer_view_permission(title.customer_id, team_id, current_user, db)
    return _invoice_title_response(db, title, team_id)


@router.put(
    "/{title_id}",
    response_model=InvoiceTitleResponse,
    summary="修改开票抬头",
    description="修改指定的开票抬头信息",
)
def update_invoice_title(
    title_id: int,
    title_data: InvoiceTitleUpdate,
    team_id: int = _TEAM,
    current_user: User = _EDIT_TITLE_USER,
    db: Session = _DB
) -> InvoiceTitleResponse:
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


@router.patch(
    "/{title_id}/set-default",
    response_model=InvoiceTitleResponse,
    summary="设置默认抬头",
    description="设置指定的开票抬头为默认抬头\uff0c自动取消原默认抬头",
)
def set_default_invoice_title(
    title_id: int,
    team_id: int = _TEAM,
    current_user: User = _SET_DEFAULT_TITLE_USER,
    db: Session = _DB
) -> InvoiceTitleResponse:
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
    team_id: int = _TEAM,
    current_user: User = _DELETE_TITLE_USER,
    db: Session = _DB
) -> dict[str, str]:
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


class _InvoiceApplicationListPayload(TypedDict):
    items: list[InvoiceApplicationResponse]
    total: int
    page: int
    page_size: int


invoice_router = APIRouter(prefix="/invoice-applications", tags=["发票申请管理"])

INVOICE_STATUS_LABELS = {
    "DRAFT": "草稿",
    "PENDING_REVIEW": "待审批",
    "APPROVED": "已批准",
    "REJECTED": "已驳回",
    "ISSUED": "已开票",
    "CANCELLED": "已取消",
}
INVOICE_TYPE_LABELS = {
    "VAT_SPECIAL": "增值税专用发票",
    "VAT_NORMAL": "增值税普通发票",
}
INVOICE_EFFECTIVE_STATUS_LABELS = {
    "ACTIVE": "有效",
    "REISSUE_PENDING": "重开中",
    "RED_OFFSET": "已冲红",
    "REISSUED": "已重开",
}
INVOICE_TAB_STATUS = {
    "pending": "PENDING_REVIEW",
    "approved": "APPROVED",
    "invoiced": "ISSUED",
}
INVOICE_TAB_STEMS = {
    "all": "全部申请",
    "pending": "待审批",
    "approved": "已批准",
    "invoiced": "已开票",
}


def _invoice_view_scope(
    db: Session, current_user: User, team_id: int, *, me: bool = False
) -> tuple[str | None, set[int] | None]:
    from app.crud.permission import permission_crud

    permission_codes = {
        permission.code
        for permission in permission_crud.get_user_permissions(db, current_user.id, team_id)
    }
    has_view_all = "invoice:view:all" in permission_codes
    has_view_own = "invoice:view:own" in permission_codes
    viewable_customer_ids = get_viewable_customer_ids(db, team_id, current_user.id)
    current_user_id = None
    visible_customer_ids = None
    if me:
        current_user_id = str(current_user.id)
    elif not has_view_all:
        if not has_view_own and viewable_customer_ids is not None and not viewable_customer_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="没有查看发票申请的权限",
            )
        if has_view_own:
            current_user_id = str(current_user.id)
        if viewable_customer_ids is not None:
            visible_customer_ids = viewable_customer_ids
    return current_user_id, visible_customer_ids


def _invoice_effective_status_from_maps(
    application: InvoiceApplication,
    reissues_by_original: dict[int, list[InvoiceReissueApplication]],
    red_offsets_by_invoice: dict[int, list[InvoiceRedOffset]],
) -> tuple[str, str]:
    reissues = reissues_by_original.get(application.id, [])
    red_offsets = red_offsets_by_invoice.get(application.id, [])
    has_open_reissue = any(
        reissue.status in {"DRAFT", "PENDING_REVIEW", "APPROVED"}
        for reissue in reissues
    )
    has_completed_reissue = any(
        reissue.status == "COMPLETED" and reissue.new_invoice_file_path
        for reissue in reissues
    )
    if has_open_reissue:
        return "REISSUE_PENDING", "REISSUE_PENDING"
    if has_completed_reissue:
        return "REISSUED", "REISSUED"
    if red_offsets:
        return "NONE", "RED_OFFSET"
    return "NONE", "ACTIVE"


def _current_invoice_file_fields(
    application: InvoiceApplication,
    reissues: Sequence[InvoiceReissueApplication],
    red_offsets: Sequence[InvoiceRedOffset],
) -> tuple[str | None, str | None, str | None, int | None]:
    latest_completed_reissue = max(
        [
            reissue
            for reissue in reissues
            if reissue.status == "COMPLETED" and reissue.new_invoice_file_path
        ],
        key=lambda reissue: (
            reissue.completed_time or reissue.last_modified_time or reissue.created_time,
            reissue.id,
        ),
        default=None,
    )
    latest_red_offset = max(
        red_offsets,
        key=lambda red_offset: (
            red_offset.red_offset_time or red_offset.last_modified_time or red_offset.created_time,
            red_offset.id,
        ),
        default=None,
    )
    if latest_completed_reissue is not None:
        return (
            "reissue_new",
            latest_completed_reissue.new_invoice_file_path,
            latest_completed_reissue.new_invoice_number,
            latest_completed_reissue.id,
        )
    if latest_red_offset is not None:
        return None, None, None, None
    return (
        "original" if application.invoice_file_path else None,
        application.invoice_file_path,
        application.invoice_number,
        None,
    )


def _populate_application_list_info(
    projection_db: Session, applications: Sequence[InvoiceApplication], team_id: int | None
) -> list[InvoiceApplicationResponse]:
    if not applications:
        return []
    application_ids = [application.id for application in applications]
    customer_ids = {application.customer_id for application in applications if application.customer_id}
    contract_ids = {application.contract_id for application in applications if application.contract_id}
    opportunity_ids = {application.opportunity_id for application in applications if application.opportunity_id}
    payment_plan_ids = {application.payment_plan_id for application in applications if application.payment_plan_id}
    user_ids = {
        int(user_id)
        for application in applications
        for user_id in (application.applicant_id, application.reviewer_id)
        if user_id and str(user_id).isdigit()
    }

    customers = {
        customer.id: customer
        for customer in projection_db.query(Customer).filter(
            Customer.id.in_(customer_ids),
            *((Customer.team_id == team_id,) if team_id is not None else ()),
        ).all()
    } if customer_ids else {}
    contracts = {
        contract.id: contract
        for contract in projection_db.query(Contract).filter(
            Contract.id.in_(contract_ids),
            *((Contract.team_id == team_id,) if team_id is not None else ()),
        ).all()
    } if contract_ids else {}
    opportunities = {
        opportunity.id: opportunity
        for opportunity in projection_db.query(Opportunity).filter(
            Opportunity.id.in_(opportunity_ids),
            *((Opportunity.team_id == team_id,) if team_id is not None else ()),
        ).all()
    } if opportunity_ids else {}
    payment_plans = {
        plan.id: plan
        for plan in projection_db.query(PaymentPlan).filter(
            PaymentPlan.id.in_(payment_plan_ids),
            *((PaymentPlan.team_id == team_id,) if team_id is not None else ()),
        ).all()
    } if payment_plan_ids else {}
    users = {
        str(user.id): user
        for user in projection_db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    reissues_by_original: dict[int, list[InvoiceReissueApplication]] = {}
    red_offsets_by_invoice: dict[int, list[InvoiceRedOffset]] = {}
    bind = projection_db.bind
    has_reissue_table = bind is None or inspect(bind).has_table(InvoiceReissueApplication.__tablename__)
    has_red_offset_table = bind is None or inspect(bind).has_table(InvoiceRedOffset.__tablename__)
    if application_ids and has_reissue_table:
        reissue_query = projection_db.query(InvoiceReissueApplication).filter(
            InvoiceReissueApplication.original_invoice_application_id.in_(application_ids)
        )
        if team_id is not None:
            reissue_query = reissue_query.filter(InvoiceReissueApplication.team_id == team_id)
        for reissue in reissue_query.all():
            reissues_by_original.setdefault(reissue.original_invoice_application_id, []).append(reissue)
    if application_ids and has_red_offset_table:
        red_offset_query = projection_db.query(InvoiceRedOffset).filter(
            InvoiceRedOffset.invoice_application_id.in_(application_ids)
        )
        if team_id is not None:
            red_offset_query = red_offset_query.filter(InvoiceRedOffset.team_id == team_id)
        for red_offset in red_offset_query.all():
            red_offsets_by_invoice.setdefault(red_offset.invoice_application_id, []).append(red_offset)

    items = []
    for application in applications:
        customer = customers.get(application.customer_id)
        contract = contracts.get(application.contract_id)
        opportunity = opportunities.get(application.opportunity_id)
        payment_plan = payment_plans.get(application.payment_plan_id)
        applicant = users.get(str(application.applicant_id)) if application.applicant_id else None
        reviewer = users.get(str(application.reviewer_id)) if application.reviewer_id else None
        reissues = reissues_by_original.get(application.id, [])
        red_offsets = red_offsets_by_invoice.get(application.id, [])
        reissue_status, invoice_effective_status = _invoice_effective_status_from_maps(
            application, reissues_by_original, red_offsets_by_invoice
        )
        current_invoice_file_kind, current_invoice_file_path, current_invoice_number, current_reissue_id = (
            _current_invoice_file_fields(application, reissues, red_offsets)
        )
        items.append(InvoiceApplicationResponse.model_validate({
            "id": application.id,
            "application_number": application.application_number,
            "customer_id": customer.public_id if customer else None,
            "contract_id": application.contract_id,
            "opportunity_id": application.opportunity_id,
            "payment_plan_id": application.payment_plan_id,
            "invoice_title_id": application.invoice_title_id,
            "invoice_amount": float(application.invoice_amount),
            "invoice_type": application.invoice_type,
            "status": application.status,
            "applicant_id": application.applicant_id,
            "reviewer_id": application.reviewer_id,
            "review_comment": application.review_comment,
            "reviewed_time": application.reviewed_time,
            "payment_record_id": application.payment_record_id,
            "invoice_title_type": application.invoice_title_type,
            "invoice_title_text": application.invoice_title_text,
            "invoice_taxpayer_id": application.invoice_taxpayer_id,
            "invoice_bank_name": application.invoice_bank_name,
            "invoice_bank_account": application.invoice_bank_account,
            "invoice_address": application.invoice_address,
            "invoice_phone": application.invoice_phone,
            "remark": application.remark,
            "created_time": application.created_time,
            "last_modified_time": application.last_modified_time,
            "invoice_file_path": application.invoice_file_path,
            "invoice_number": application.invoice_number,
            "issued_time": application.issued_time,
            "customer_name": customer.account_name if customer else None,
            "contract_name": contract.contract_name if contract else None,
            "opportunity_name": opportunity.opportunity_name if opportunity else None,
            "payment_plan_stage_name": payment_plan.stage_name if payment_plan else None,
            "invoice_title_title": application.invoice_title_text,
            "applicant_name": applicant.name if applicant else None,
            "reviewer_name": reviewer.name if reviewer else None,
            "reissue_status": reissue_status,
            "invoice_effective_status": invoice_effective_status,
            "current_invoice_file_kind": current_invoice_file_kind,
            "current_invoice_file_path": current_invoice_file_path,
            "current_invoice_number": current_invoice_number,
            "current_reissue_id": current_reissue_id,
            "red_offsets": [_populate_red_offset_info(projection_db, red_offset) for red_offset in red_offsets],
            "reissue_applications": [
                _populate_reissue_application_info(projection_db, reissue) for reissue in reissues
            ],
        }))
    return items


def _invoice_export_row(
    application: InvoiceApplication,
    *,
    customer: Customer | None,
    contract: Contract | None,
    applicant: User | None,
    invoice_effective_status: str,
) -> dict[str, object]:
    status_value = getattr(application.status, "value", application.status)
    invoice_type = getattr(application.invoice_type, "value", application.invoice_type)
    return {
        "application_number": application.application_number,
        "customer_name": customer.account_name if customer else None,
        "contract_name": contract.contract_name if contract else None,
        "invoice_type": INVOICE_TYPE_LABELS.get(invoice_type, invoice_type),
        "invoice_amount": float(application.invoice_amount),
        "invoice_title_text": application.invoice_title_text,
        "status": INVOICE_STATUS_LABELS.get(status_value, status_value),
        "invoice_effective_status": INVOICE_EFFECTIVE_STATUS_LABELS.get(
            invoice_effective_status, invoice_effective_status
        ),
        "applicant_name": applicant.name if applicant else None,
        "created_time": application.created_time,
    }


def _iter_invoice_export_rows(
    stream: Iterable[InvoiceApplication],
    team_id: int,
    projection_session_factory: Callable[[], Session] = SessionLocal,
) -> Iterator[dict[str, object]]:
    for batch in iter_batches(stream, 500):
        projection_db = projection_session_factory()
        try:
            if not batch:
                continue
            application_ids = [application.id for application in batch]
            customer_ids = {application.customer_id for application in batch if application.customer_id}
            contract_ids = {application.contract_id for application in batch if application.contract_id}
            user_ids = {
                int(application.applicant_id)
                for application in batch
                if application.applicant_id and str(application.applicant_id).isdigit()
            }
            customers = {
                customer.id: customer
                for customer in projection_db.query(Customer).filter(
                    Customer.id.in_(customer_ids),
                    Customer.team_id == team_id,
                ).all()
            } if customer_ids else {}
            contracts = {
                contract.id: contract
                for contract in projection_db.query(Contract).filter(
                    Contract.id.in_(contract_ids),
                    Contract.team_id == team_id,
                ).all()
            } if contract_ids else {}
            users = {
                str(user.id): user
                for user in projection_db.query(User).filter(User.id.in_(user_ids)).all()
            } if user_ids else {}
            reissues_by_original: dict[int, list[InvoiceReissueApplication]] = {}
            red_offsets_by_invoice: dict[int, list[InvoiceRedOffset]] = {}
            bind = projection_db.bind
            has_reissue_table = bind is None or inspect(bind).has_table(InvoiceReissueApplication.__tablename__)
            has_red_offset_table = bind is None or inspect(bind).has_table(InvoiceRedOffset.__tablename__)
            if application_ids and has_reissue_table:
                reissue_query = projection_db.query(InvoiceReissueApplication).filter(
                    InvoiceReissueApplication.original_invoice_application_id.in_(application_ids),
                    InvoiceReissueApplication.team_id == team_id,
                )
                for reissue in reissue_query.all():
                    reissues_by_original.setdefault(reissue.original_invoice_application_id, []).append(reissue)
            if application_ids and has_red_offset_table:
                red_offset_query = projection_db.query(InvoiceRedOffset).filter(
                    InvoiceRedOffset.invoice_application_id.in_(application_ids),
                    InvoiceRedOffset.team_id == team_id,
                )
                for red_offset in red_offset_query.all():
                    red_offsets_by_invoice.setdefault(red_offset.invoice_application_id, []).append(red_offset)
            for application in batch:
                _, invoice_effective_status = _invoice_effective_status_from_maps(
                    application, reissues_by_original, red_offsets_by_invoice
                )
                yield _invoice_export_row(
                    application,
                    customer=customers.get(application.customer_id),
                    contract=contracts.get(application.contract_id),
                    applicant=users.get(str(application.applicant_id)) if application.applicant_id else None,
                    invoice_effective_status=invoice_effective_status,
                )
        finally:
            projection_db.close()





@invoice_router.post(
    "",
    response_model=InvoiceApplicationResponse,
    summary="创建发票申请",
    description="创建新的发票申请\uff0c自动关联业务上下文\uff08客户、合同、商机、回款计划\uff09",
)
def create_invoice_application(
    application_data: InvoiceApplicationCreate,
    team_id: int = _TEAM,
    current_user: User = _CREATE_INVOICE_USER,
    db: Session = _DB
) -> InvoiceApplicationResponse:
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
        ) from e


@invoice_router.get(
    "",
    response_model=InvoiceApplicationListResponse,
    summary="查询发票申请列表",
    description="支持按客户、合同、状态等多条件筛选发票申请",
)
def list_invoice_applications(
    customer_id: str | None = Query(None, description="客户对外ID"),
    contract_id: int | None = Query(None, description="合同ID"),
    payment_plan_id: int | None = Query(None, description="回款计划ID"),
    application_status: str | None = Query(None, alias="status", description="申请状态\uff0c多个值用逗号分隔"),
    status_exclude: str | None = Query(None, description="排除的申请状态\uff0c多个值用逗号分隔"),
    invoice_type: str | None = Query(None, description="发票类型\uff0c多个值用逗号分隔"),
    invoice_type_exclude: str | None = Query(None, description="排除的发票类型\uff0c多个值用逗号分隔"),
    invoice_effective_status: str | None = Query(
        None,
        description="发票有效状态\uff0c多个值用逗号分隔\uff1aACTIVE/REISSUE_PENDING/RED_OFFSET/REISSUED",
    ),
    applicant_id: str | None = Query(None, description="申请人ID"),
    keyword: str | None = Query(None, description="关键词\uff0c支持申请编号、客户、合同、抬头、税号、发票号码"),
    search: str | None = Query(None, description="统一搜索\uff0c可搜索申请编号、客户、合同、抬头、税号或发票号码"),
    created_time_start: date | None = _CREATED_TIME_START,
    created_time_end: date | None = _CREATED_TIME_END,
    order_by: str | None = Query(None, description="排序字段"),
    order_dir: str | None = Query(None, description="排序方向 asc/desc"),
    filters: str | None = Query(None, description="通用筛选条件 JSON"),
    sorts: str | None = Query(None, description="通用排序条件 JSON"),
    page: int | None = Query(None, ge=1, description="页码\uff08兼容前端 page/page_size\uff09"),
    page_size: int | None = Query(None, ge=1, le=100, description="每页记录数\uff08兼容前端 page/page_size\uff09"),
    me: bool = Query(False, description="是否只查询当前用户申请的数据"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB
) -> _InvoiceApplicationListPayload:
    """
    查询发票申请列表\uff08添加权限隔离\uff09

    权限逻辑\uff1a
    - invoice:view:all → 可查看所有发票申请
    - 指定 customer_id 且能查看该客户 → 返回该客户树上的发票
    - invoice:view:own / 客户可见范围 → 自己申请的发票\uff0c或所属客户对自己可见的发票
    """
    from app.crud.permission import permission_crud

    # 权限检查
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    has_view_all = "invoice:view:all" in permission_codes
    has_view_own = "invoice:view:own" in permission_codes
    viewable_customer_ids = get_viewable_customer_ids(db, team_id, current_user.id)

    effective_limit = page_size if page_size is not None else limit
    effective_skip = (page - 1) * effective_limit if page is not None else skip

    internal_customer_id = None
    if customer_id:
        customer = check_customer_view_permission(customer_id, team_id, current_user, db)
        internal_customer_id = customer.id

    if (
        not has_view_all
        and not has_view_own
        and internal_customer_id is None
        and viewable_customer_ids is not None
        and not viewable_customer_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有查看发票申请的权限"
        )

    # 数据所有权隔离
    current_user_id = None
    visible_customer_ids = None
    if me:
        current_user_id = str(current_user.id)
    elif not has_view_all and internal_customer_id is None:
        if has_view_own:
            current_user_id = str(current_user.id)
        if viewable_customer_ids is not None:
            visible_customer_ids = viewable_customer_ids

    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )

    applications, total = run_or_400(lambda: invoice_application_crud.list_applications(
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
        visible_customer_ids=visible_customer_ids,
        keyword=keyword,
        search=search,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        order_by=order_by,
        order_dir=order_dir,
        filters=parsed_filters,
        sorts=parsed_sorts,
    ))

    populated_applications = _populate_application_list_info(db, applications, team_id)

    # 计算页码(skip/limit + 1)
    current_page = page if page is not None else (effective_skip // effective_limit + 1 if effective_limit > 0 else 1)

    return {
        "items": populated_applications,
        "total": total,
        "page": current_page,
        "page_size": effective_limit
    }


@invoice_router.post(
    "/export",
    dependencies=[Depends(require_permission("invoice:export"))],
    summary="导出发票申请列表",
    description="按当前筛选条件导出全部匹配发票申请为 Excel",
)
def export_invoice_applications(
    request: InvoiceListExportRequest,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB,
) -> FileResponse:
    current_user_id, visible_customer_ids = _invoice_view_scope(db, current_user, team_id)
    query = run_or_400(lambda: invoice_application_crud.build_list_query(
        db,
        team_id=team_id,
        status=INVOICE_TAB_STATUS.get(request.tab),
        current_user_id=current_user_id,
        visible_customer_ids=visible_customer_ids,
        search=request.search,
        filters=request.filters,
        sorts=request.sorts,
    ))
    stream = query.enable_eagerloads(False).execution_options(stream_results=True).yield_per(500)
    rows = _iter_invoice_export_rows(stream, team_id, projection_session_factory=SessionLocal)
    generated = run_list_export_or_400(lambda: create_list_export_file(
        catalog=INVOICES_LIST_EXPORT_CATALOG,
        selected_keys=request.fields,
        rows=rows,
        file_stem=f"发票申请列表-{INVOICE_TAB_STEMS.get(request.tab, '全部申请')}",
    ))
    return list_export_file_response(generated)



@invoice_router.post(
    "/{application_id}/reissues",
    response_model=InvoiceReissueApplicationResponse,
    summary="创建发票重开申请",
    description="对已开票的发票申请创建重开申请\uff0c原发票不被替换",
)
def create_invoice_reissue_application(
    application_id: int,
    reissue_data: InvoiceReissueApplicationCreate,
    team_id: int = _TEAM,
    current_user: User = _CREATE_REISSUE_USER,
    db: Session = _DB,
) -> InvoiceReissueApplicationResponse:
    original_invoice = check_invoice_write_scope(application_id, team_id, current_user, db)
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
        ) from e


@invoice_router.put(
    "/reissues/{reissue_id}",
    response_model=InvoiceReissueApplicationResponse,
    summary="修改发票重开申请",
    description="仅草稿或已拒绝状态可修改",
)
def update_invoice_reissue_application(
    reissue_id: int,
    reissue_data: InvoiceReissueApplicationUpdate,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB,
) -> InvoiceReissueApplicationResponse:
    reissue = invoice_reissue_application_crud.get_by_id(db, reissue_id, team_id)
    if not reissue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票重开申请不存在")
    if reissue.applicant_id != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能编辑自己申请的发票重开申请")

    try:
        updated = invoice_reissue_application_crud.update(db, reissue, reissue_data)
        return _populate_reissue_application_info(db, updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@invoice_router.post(
    "/reissues/{reissue_id}/complete",
    response_model=InvoiceReissueApplicationResponse,
    summary="完成发票重开",
    description="财务上传红字发票和新蓝字发票后完成重开",
)
async def complete_invoice_reissue(
    reissue_id: int,
    red_file: UploadFile = _COMPLETE_RED_FILE,
    new_file: UploadFile = _COMPLETE_NEW_FILE,
    red_invoice_number: str | None = Form(None, description="红字发票号码"),
    new_invoice_number: str | None = Form(None, description="新蓝字发票号码"),
    team_id: int = _TEAM,
    current_user: User = _COMPLETE_REISSUE_USER,
    db: Session = _DB,
) -> InvoiceReissueApplicationResponse:
    _ = current_user  # Permission is enforced by the dependency; no actor is needed here.
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@invoice_router.get(
    "/reissues/{reissue_id}/{file_kind}-file",
    summary="下载发票重开相关文件",
    description="下载红字发票或新蓝字发票文件\uff0cfile_kind 为 red 或 new",
)
async def download_invoice_reissue_file(
    reissue_id: int,
    file_kind: Literal["red", "new"],
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB,
) -> Response:
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
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB,
) -> Response:
    red_offset = invoice_red_offset_crud.get_by_id(db, red_offset_id, team_id)
    if not red_offset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票冲红记录不存在")

    check_invoice_view_permission(red_offset.invoice_application_id, team_id, current_user, db)
    filename_base = f"red-offset-{red_offset.red_invoice_number or red_offset_id}"
    return _download_invoice_path(red_offset.red_invoice_file_path, filename_base)


@invoice_router.get(
    "/{application_id}",
    response_model=InvoiceApplicationResponse,
    summary="获取发票申请详情",
    description="获取指定发票申请的完整信息及关联业务数据",
)
def get_invoice_application(
    application_id: int,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB
) -> InvoiceApplicationResponse:
    application = check_invoice_view_permission(application_id, team_id, current_user, db)

    return _populate_application_info(db, application, team_id)


@invoice_router.put(
    "/{application_id}",
    response_model=InvoiceApplicationResponse,
    summary="修改发票申请",
    description="修改指定的发票申请信息\uff08仅草稿状态可编辑\uff09",
)
def update_invoice_application(
    application_id: int,
    application_data: InvoiceApplicationUpdate,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB
) -> InvoiceApplicationResponse:
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
        ) from e


@invoice_router.post(
    "/{application_id}/mark-issued",
    response_model=InvoiceApplicationResponse,
    summary="标记为已开票",
    description="审批通过后执行开票业务动作\uff0c可选上传发票文件和填写发票号码",
)
async def mark_invoice_issued(
    application_id: int,
    file: UploadFile | None = _ISSUED_FILE,
    invoice_number: str | None = Form(None, description="发票号码\uff08可选\uff09"),
    team_id: int = _TEAM,
    current_user: User = _MARK_ISSUED_USER,
    db: Session = _DB
) -> InvoiceApplicationResponse:
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
            detail="发票未通过审批\uff0c不可开票"
        )

    if application.status != InvoiceApplicationStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"发票申请状态为 {application.status}\uff0c不可开票"
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
            ) from e

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
        # Building the refresh requires a persisted invoice and raises if the CRUD returned None.
        issued_application = cast("InvoiceApplication", issued_application)
        try:
            notify_request = outbound_notification_job_service.enqueue_issued(
                db,
                team_id=team_id,
                business_type=BusinessType.INVOICE,
                business_id=int(issued_application.id),
                recipient_user_id=int(approval.submitter_id),
                actor_id=str(current_user.id),
                approval_id=int(approval.id) if getattr(approval, "id", None) is not None else None,
                button_path="/invoices",
            )
            outbound_notification_job_service.commit_and_kick(db, notify_request)
        except Exception as notify_error:
            logger.error(
                f"[Invoice] Issue notification enqueue failed: application_id={application_id}, error={notify_error!s}"
            )
        return _populate_application_info(db, issued_application, team_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@invoice_router.post(
    "/{application_id}/red-offset",
    response_model=InvoiceApplicationResponse,
    summary="冲红发票",
    description="财务上传红字发票后\uff0c将已开票发票标记为已冲红\uff1b不进入审批流程",
)
async def red_offset_invoice(
    application_id: int,
    file: UploadFile = _RED_OFFSET_FILE,
    red_invoice_number: str | None = Form(None, description="红字发票号码"),
    reason: str | None = Form(None, description="冲红原因"),
    team_id: int = _TEAM,
    current_user: User = _RED_OFFSET_USER,
    db: Session = _DB,
) -> InvoiceApplicationResponse:
    application = invoice_application_crud.get_by_id(db, application_id, team_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票申请不存在")

    try:
        invoice_red_offset_crud.assert_can_create_manual(db, application, team_id=team_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        red_file_path = file_storage_service.save_invoice_file(
            team_id=team_id,
            invoice_id=application_id,
            filename=file.filename or "",
            content=await file.read(),
        )
    except FileStorageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@invoice_router.delete(
    "/{application_id}",
    response_model=MessageResponse,
    summary="删除发票申请",
    description="删除指定的发票申请\uff08审批中或审批通过后不可删除\uff09",
)
def delete_invoice_application(
    application_id: int,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB
) -> dict[str, str]:
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
        ) from e


# ============================================================================
# Task 4: 发票文件下载端点(GET /invoice-applications/{application_id}/file)
# ============================================================================
# 设计要点:
# - application_id: 发票申请 ID
# - 权限:get_current_active_user(登录用户即可,发票文件无敏感信息)
# - 安全校验:FileStorageService.get_full_path 防路径穿越
# - 文件存在检查:os.path.exists
# - Content-Type 映射:按扩展名设置正确的 MIME 类型
# - Content-Disposition:attachment,文件名用 invoice_number 或 application_id
# ============================================================================


@invoice_router.get(
    "/{application_id}/file",
    summary="下载发票文件\uff08Task 4\uff09",
    description="""
下载已上传的发票文件。

**功能说明\uff1a**
- 仅已开票状态\uff08ISSUED\uff09的发票可下载
- 自动设置正确的 Content-Type\uff08PDF/JPG/PNG/OFD\uff09
- 文件名使用发票号码或申请 ID

**路径参数\uff1a**
- application_id: 发票申请 ID

**返回\uff1a**
- 文件内容\uff08二进制流\uff09
- Content-Type: application/pdf / image/jpeg / image/png / application/octet-stream
- Content-Disposition: attachment

**错误情况\uff1a**
- 发票申请不存在\uff1a404
- 未上传文件\uff1a404
- 文件不存在\uff1a404
- 文件路径非法\uff1a400
""",
)
async def download_invoice_file(
    application_id: int,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB,
) -> Response:
    """下载发票文件"""

    application = check_invoice_view_permission(application_id, team_id, current_user, db)

    if not application.invoice_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该发票未上传文件",
        )

    return _download_invoice_path(
        application.invoice_file_path, application.invoice_number or f"invoice_{application_id}"
    )


@invoice_router.get(
    "/payment-plans/{payment_plan_id}/invoices",
    response_model=PaymentPlanInvoiceSummary,
    summary="获取回款计划关联发票",
    description="查询指定回款计划关联的所有发票申请及状态",
)
def get_payment_plan_invoices(
    payment_plan_id: int,
    team_id: int = _TEAM,
    current_user: User = _ACTIVE_USER,
    db: Session = _DB
) -> PaymentPlanInvoiceSummary:
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


def _populate_application_info(
    db: Session, application: InvoiceApplication, team_id: int | None = None
) -> InvoiceApplicationResponse:
    """填充发票申请完整响应信息

    Changes:
    - 返回 InvoiceApplicationResponse\uff08而非 dict\uff09类型安全
    - 添加 invoice_file_path / invoice_number / issued_time\uff08修复 bug\uff09
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
    reissue_status, invoice_effective_status = _invoice_effective_status_from_maps(
        application,
        {application.id: reissues},
        {application.id: red_offsets},
    )
    current_invoice_file_kind, current_invoice_file_path, current_invoice_number, current_reissue_id = (
        _current_invoice_file_fields(application, reissues, red_offsets)
    )

    return InvoiceApplicationResponse.model_validate({
        "id": application.id,
        "application_number": application.application_number,
        "customer_id": customer.public_id if customer else None,
        "contract_id": application.contract_id,
        "opportunity_id": application.opportunity_id,
        "payment_plan_id": application.payment_plan_id,
        "invoice_title_id": application.invoice_title_id,
        "invoice_amount": float(application.invoice_amount),
        "invoice_type": application.invoice_type,
        "status": application.status,
        "applicant_id": application.applicant_id,
        "reviewer_id": application.reviewer_id,
        "review_comment": application.review_comment,
        "reviewed_time": application.reviewed_time,
        "payment_record_id": application.payment_record_id,
        "invoice_title_type": application.invoice_title_type,
        "invoice_title_text": application.invoice_title_text,
        "invoice_taxpayer_id": application.invoice_taxpayer_id,
        "invoice_bank_name": application.invoice_bank_name,
        "invoice_bank_account": application.invoice_bank_account,
        "invoice_address": application.invoice_address,
        "invoice_phone": application.invoice_phone,
        "remark": application.remark,
        "created_time": application.created_time,
        "last_modified_time": application.last_modified_time,

        # Bug 修复:添加三个缺失字段
        "invoice_file_path": application.invoice_file_path,
        "invoice_number": application.invoice_number,
        "issued_time": application.issued_time,

        # 关联业务信息
        "customer_name": customer.account_name if customer else None,
        "contract_name": contract.contract_name if contract else None,
        "opportunity_name": opportunity.opportunity_name if opportunity else None,
        "payment_plan_stage_name": payment_plan.stage_name if payment_plan else None,
        "invoice_title_title": application.invoice_title_text,
        "applicant_name": applicant_name,
        "reviewer_name": reviewer_name,
        "reissue_status": reissue_status,
        "invoice_effective_status": invoice_effective_status,
        "current_invoice_file_kind": current_invoice_file_kind,
        "current_invoice_file_path": current_invoice_file_path,
        "current_invoice_number": current_invoice_number,
        "current_reissue_id": current_reissue_id,
        "red_offsets": [_populate_red_offset_info(db, red_offset) for red_offset in red_offsets],
        "reissue_applications": [_populate_reissue_application_info(db, reissue) for reissue in reissues],
    })


def _populate_red_offset_info(db: Session, red_offset: InvoiceRedOffset) -> InvoiceRedOffsetResponse:
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


def _populate_reissue_application_info(
    db: Session, reissue: InvoiceReissueApplication
) -> InvoiceReissueApplicationResponse:
    applicant_name = None
    if reissue.applicant_id:
        applicant = db.query(User).filter(User.id == int(reissue.applicant_id)).first()
        if applicant:
            applicant_name = applicant.name

    return InvoiceReissueApplicationResponse.model_validate({
        "id": reissue.id,
        "application_number": reissue.application_number,
        "original_invoice_application_id": reissue.original_invoice_application_id,
        "applicant_id": reissue.applicant_id,
        "applicant_name": applicant_name,
        "reason": reissue.reason,
        "status": reissue.status,
        "approval_phase": reissue.approval_phase,
        "invoice_title_type": reissue.invoice_title_type,
        "invoice_title_text": reissue.invoice_title_text,
        "invoice_taxpayer_id": reissue.invoice_taxpayer_id,
        "invoice_bank_name": reissue.invoice_bank_name,
        "invoice_bank_account": reissue.invoice_bank_account,
        "invoice_address": reissue.invoice_address,
        "invoice_phone": reissue.invoice_phone,
        "invoice_amount": reissue.invoice_amount,
        "invoice_type": reissue.invoice_type,
        "red_invoice_file_path": reissue.red_invoice_file_path,
        "red_invoice_number": reissue.red_invoice_number,
        "red_issued_time": reissue.red_issued_time,
        "new_invoice_file_path": reissue.new_invoice_file_path,
        "new_invoice_number": reissue.new_invoice_number,
        "new_issued_time": reissue.new_issued_time,
        "completed_time": reissue.completed_time,
        "created_time": reissue.created_time,
        "last_modified_time": reissue.last_modified_time,
    })


def _download_invoice_path(file_path: str, filename_base: str) -> Response:
    try:
        full_path = file_storage_service.get_full_path(file_path)
    except FileStorageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件路径非法") from e

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
