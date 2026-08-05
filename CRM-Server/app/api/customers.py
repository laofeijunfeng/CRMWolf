import logging
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    check_customer_delete_permission,
    check_customer_edit_permission,
    check_customer_member_manage_permission,
    check_customer_view_permission,
    get_current_active_user,
    get_current_user_team,
    require_permission,
)
from app.crud.contract import contract_crud
from app.crud.customer import contact_crud, customer_crud
from app.crud.customer_member import customer_member_crud
from app.crud.invoice import invoice_application_crud, invoice_title_crud
from app.crud.lead import lead_crud
from app.crud.team import team_crud
from app.crud.user import user_crud
from app.models.customer import Contact
from app.services.industry_display_service import industry_display_service
from app.schemas.common import PaginatedResponse
from app.schemas.contract import ContractListResponse, ContractStatusEnum
from app.schemas.customer import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    ConvertLeadToCustomer,
    ConvertResponse,
    CustomerAssignRequest,
    CustomerAssignResponse,
    CustomerClaimRequest,
    CustomerCreate,
    CustomerDetailResponse,
    CustomerIndustryOption,
    CustomerIntelligenceBatchRebuildRequest,
    CustomerIntelligenceBatchRebuildResponse,
    CustomerIntelligenceRegenerateRequest,
    CustomerIntelligenceRetryDueResponse,
    CustomerIntelligenceRunDiagnosticListResponse,
    CustomerIntelligenceRunDiagnosticResponse,
    CustomerListResponse,
    CustomerLoseRequest,
    CustomerMemberCandidate,
    CustomerMemberCreate,
    CustomerMemberResponse,
    CustomerMemberUpdate,
    CustomerMemberUserInfo,
    CustomerResponse,
    CustomerReturnRequest,
    CustomerReturnResponse,
    CustomerStatusUpdate,
    CustomerUpdate,
    MessageResponse,
    StatisticsResponse,
    TrendResponse,
)
from app.schemas.invoice import InvoiceApplicationResponse, InvoiceTitleResponse
from app.schemas.payment import PaymentPlanResponse
from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent
from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service
from app.services.customer_intelligence_run_service import CustomerIntelligenceRunDiagnostic
from app.api.invoices import _invoice_title_response, _populate_application_info

router = APIRouter(prefix="/v1/customers", tags=["客户管理"])
logger = logging.getLogger(__name__)


def _customer_name_conflict_error(
    db: Session,
    account_name: str,
    team_id: int,
    exclude_customer_id: Optional[int] = None,
    allowed_source_lead_id: Optional[int] = None,
) -> Optional[str]:
    existing_customer = customer_crud.get_by_name(db, account_name, team_id)
    if existing_customer and existing_customer.id != exclude_customer_id:
        return "客户名称已存在"
    existing_lead = lead_crud.get_by_name(db, account_name, team_id)
    excluded_customer = customer_crud.get_by_id(db, exclude_customer_id, team_id) if exclude_customer_id else None
    if existing_lead and existing_lead.id != allowed_source_lead_id and not (
        excluded_customer and excluded_customer.source_lead_id == existing_lead.id
    ):
        return "该名称已存在线索，请先处理或转化线索"
    return None


def _ensure_customer_name_available(
    db: Session,
    account_name: str,
    team_id: int,
    exclude_customer_id: Optional[int] = None,
    allowed_source_lead_id: Optional[int] = None,
) -> None:
    error = _customer_name_conflict_error(
        db,
        account_name,
        team_id,
        exclude_customer_id=exclude_customer_id,
        allowed_source_lead_id=allowed_source_lead_id,
    )
    if error:
        logger.warning(
            "客户名称校验失败: team_id=%s account_name=%s reason=%s",
            team_id,
            account_name,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )


def _get_customer_or_404(db: Session, customer_public_id: str, team_id: int):
    customer = customer_crud.get_by_public_id(db, customer_public_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )
    return customer


def _get_viewable_customer(db: Session, customer_public_id: str, team_id: int, current_user):
    return check_customer_view_permission(customer_public_id, team_id, current_user, db)


def _get_editable_customer(db: Session, customer_public_id: str, team_id: int, current_user):
    return check_customer_edit_permission(customer_public_id, team_id, current_user, db)


async def _schedule_contact_intelligence_refresh(
    db: Session,
    contact: Contact,
    *,
    trigger_type: Literal[
        "customer_contact_created",
        "customer_contact_updated",
        "customer_contact_deleted",
    ],
    actor_id: str,
) -> None:
    from app.services.customer_intelligence_event_service import customer_intelligence_event_service

    event = customer_intelligence_event_service.from_contact(
        contact,
        trigger_type=trigger_type,
        actor_id=actor_id,
    )
    if event is None:
        return
    await _schedule_customer_intelligence_event_refresh(db, event)


async def _schedule_customer_intelligence_event_refresh(
    db: Session,
    event: CustomerIntelligenceEvent,
) -> None:
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    await customer_intelligence_refresh_service.trigger_committed_event_refresh(
        db,
        event=event,
        scope="brief",
    )


def _get_user_basic_info(db: Session, user_id: Optional[str]) -> Optional[dict]:
    if not user_id:
        return None

    user_data = db.execute(text("""
        SELECT id, name, email, mobile, avatar_url
        FROM users
        WHERE id = CAST(:user_id AS SIGNED)
    """), {"user_id": user_id}).first()

    if not user_data:
        return None

    return {
        "id": str(user_data[0]),
        "name": user_data[1],
        "email": user_data[2],
        "mobile": user_data[3],
        "avatar_url": user_data[4],
    }


def _contract_response_base(contract) -> dict:
    if not getattr(contract, "customer", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="合同关联客户数据异常",
        )
    opportunity = getattr(contract, "opportunity", None)
    return {
        "id": contract.id,
        "contract_number": contract.contract_number,
        "contract_name": contract.contract_name,
        "customer_id": contract.customer.public_id,
        "opportunity_id": opportunity.public_id if opportunity else None,
        "signing_contact_id": contract.signing_contact_id,
        "user_count": contract.user_count,
        "total_amount": contract.total_amount,
        "license_type": contract.license_type,
        "subscription_years": contract.subscription_years,
        "standard_unit_price": contract.standard_unit_price,
        "status": contract.status,
        "signing_date": contract.signing_date,
        "effective_date": contract.effective_date,
        "expiry_date": contract.expiry_date,
        "owner_id": contract.owner_id,
        "creator_id": contract.creator_id,
        "created_time": contract.created_time,
        "last_modified_time": contract.last_modified_time,
        "contract_file_path": contract.contract_file_path,
        "contract_file_name": contract.contract_file_name,
        "contract_file_size": contract.contract_file_size,
        "contract_file_mime_type": contract.contract_file_mime_type,
    }


def _contract_status_info(status_value) -> Optional[dict]:
    if not status_value:
        return None

    raw_status = status_value.value if hasattr(status_value, "value") else status_value
    try:
        status_enum = ContractStatusEnum(raw_status)
    except ValueError:
        return None

    return {
        "code": status_enum.value,
        "name": status_enum.description,
    }


def _contact_response(contact: Contact, customer_public_id: str) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        customer_id=customer_public_id,
        name=contact.name,
        gender=contact.gender,
        position=contact.position,
        is_decision_maker=bool(contact.is_decision_maker),
        mobile=contact.mobile,
        email=contact.email,
        wechat_id=contact.wechat_id,
        remark=contact.remark,
        reports_to=contact.reports_to,
        is_primary=bool(contact.is_primary),
        created_time=contact.created_time,
    )


def _customer_response(db: Session, customer) -> CustomerResponse:
    source_lead_public_id = None
    if customer.source_lead_id:
        source_lead = lead_crud.get_by_id(db, customer.source_lead_id, customer.team_id)
        source_lead_public_id = source_lead.public_id if source_lead else None

    return CustomerResponse(**{
        "id": customer.public_id,
        "public_id": customer.public_id,
        "account_name": customer.account_name,
        "industry": customer.industry,
        "city": customer.city,
        "address": customer.address,
        "company_scale": customer.company_scale,
        "source": customer.source,
        "status": customer.status,
        "owner_id": customer.owner_id,
        "source_lead_id": source_lead_public_id,
        "default_procurement_method_id": customer.default_procurement_method_id,
        "loss_reason": customer.loss_reason,
        "return_reason": customer.return_reason,
        "returned_time": customer.returned_time,
        "creator_id": customer.creator_id,
        "created_time": customer.created_time,
        "last_modified_time": customer.last_modified_time,
        "version": customer.version,
        "company_background": customer.company_background,
        "company_website": customer.company_website,
        "main_business": customer.main_business,
        "similar_customers": customer.similar_customers,
        "project_background": customer.project_background,
        "profile_status": customer.profile_status,
        "profile_generated_time": customer.profile_generated_time,
        "profile_error_message": customer.profile_error_message,
        "license_expiry_date": customer.license_expiry_date,
        "license_type": customer.license_type,
    })


def _customer_intelligence_run_response(
    db: Session,
    team_id: int,
    diagnostic: CustomerIntelligenceRunDiagnostic,
) -> CustomerIntelligenceRunDiagnosticResponse:
    result_summary = dict(diagnostic.result)
    result_summary.pop("route", None)
    customer = customer_crud.get_by_id(db, diagnostic.customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="客户智能任务关联客户数据异常",
        )
    return CustomerIntelligenceRunDiagnosticResponse(
        id=diagnostic.id,
        request_id=diagnostic.request_id,
        customer_id=customer.public_id,
        actor_id=diagnostic.actor_id,
        trigger_type=diagnostic.trigger_type,
        scope=diagnostic.scope,
        status=diagnostic.status,
        attempt_count=diagnostic.attempt_count,
        max_attempts=diagnostic.max_attempts,
        route_label=_customer_intelligence_route_label(diagnostic.route),
        result=result_summary,
        visible_trace=diagnostic.visible_trace,
        trace_events=diagnostic.trace_events,
        error_message=diagnostic.error_message,
        created_time=diagnostic.created_time,
        started_time=diagnostic.started_time,
        finished_time=diagnostic.finished_time,
        next_retry_at=diagnostic.next_retry_at,
        last_duration_ms=diagnostic.last_duration_ms,
    )


def _customer_intelligence_route_label(route: str | None) -> Optional[str]:
    if route == "refresh_profile":
        return "刷新客户档案"
    if route == "refresh_brief":
        return "刷新客户概况"
    if route == "answer_customer_question":
        return "回答客户问题"
    return None


@router.get("/industries", response_model=List[CustomerIndustryOption], summary="获取客户所属行业选项", description="""
获取客户所属行业的下拉选项列表（用于客户创建、编辑等场景）。

**业务规则：**
- 返回预定义的行业枚举列表
- 轻量级接口，无需查询数据库
- 通过枚举实现数据统一管理
""")
def get_customer_industries(
    current_user = Depends(get_current_active_user)
):
    from app.models.customer import CustomerIndustry
    
    industries = []
    for industry in CustomerIndustry:
        industries.append(CustomerIndustryOption(
            value=industry.name,
            label=industry.value
        ))
    return industries


@router.post("/convert-from-lead", response_model=ConvertResponse, status_code=status.HTTP_201_CREATED, summary="线索转化", description="根据线索ID创建客户和主联系人，AI自动生成档案")
async def convert_from_lead(
    data: ConvertLeadToCustomer,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service
    from app.services.feishu import feishu_service

    source_lead = lead_crud.get_by_public_id(db, data.lead_id, team_id)
    if not source_lead:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="线索不存在",
        )
    _ensure_customer_name_available(
        db,
        data.account_name or source_lead.lead_name,
        team_id,
        allowed_source_lead_id=source_lead.id,
    )

    try:
        customer, contact = customer_crud.convert_from_lead(
            db=db,
            lead_id=source_lead.id,
            account_name=data.account_name,
            address=data.address,
            default_procurement_method_id=data.default_procurement_method_id,
            creator_id=str(current_user.id),
            operator_name=current_user.name,
            team_id=team_id
        )

        # 设置档案状态为 PENDING
        customer_crud.update_profile_status(db, customer.id, "PENDING")

        # 触发客户智能档案生成（异步，进入 LangGraph 统一编排）
        await customer_intelligence_refresh_service.trigger_customer_created_refresh(
            db,
            team_id=team_id,
            customer_id=customer.id,
            actor_id=str(current_user.id),
            source_lead_id=source_lead.id,
        )

        await feishu_service.notify_account_created(
            customer.owner_id,
            customer.account_name,
            contact.name
        )

        return ConvertResponse(
            customer_id=customer.public_id,
            contact_id=contact.id,
            message="转化成功，客户智能档案正在整理"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{customer_id}/contracts", response_model=List[ContractListResponse], summary="获取客户合同列表", description="""
获取指定客户的所有合同，支持按状态筛选和分页查询。

**功能说明：**
- 查询客户的所有合同
- 支持按合同状态筛选
- 支持分页查询
- 返回合同详细信息

**业务场景：**
- 查看客户的合同历史
- 了解客户的合同状态
- 客户详情页展示合同列表

**路径参数：**
- customer_id: 客户对外ID

**查询参数：**
- status: 合同状态筛选（可选）
- skip: 分页跳过记录数（默认0）
- limit: 每页记录数（默认20，最大100）

**返回字段：**
- 合同基本信息：ID、名称、编号、金额等
- 客户信息：客户名称
- 商机信息：商机名称
- 负责人信息：负责人姓名
""")
def get_customer_contracts(
    customer_id: str,
    status: Optional[str] = Query(None, description="合同状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.contract import ContractStatus

    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    internal_customer_id = customer.id

    contracts, total = contract_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        customer_id=internal_customer_id,
        status=ContractStatus[status] if status else None
    )

    result = []
    for contract in contracts:
        opportunity_info = None
        if contract.opportunity_id:
            opportunity_data = db.execute(text("""
                SELECT public_id, opportunity_name
                FROM crm_opportunities
                WHERE id = :opportunity_id
            """), {"opportunity_id": contract.opportunity_id}).first()

            if opportunity_data:
                opportunity_info = {
                    "id": opportunity_data[0],
                    "opportunity_name": opportunity_data[1],
                }

        contract_dict = _contract_response_base(contract)
        contract_dict.update({
            "customer_info": {
                "id": customer.public_id,
                "public_id": customer.public_id,
                "account_name": customer.account_name,
            },
            "opportunity_info": opportunity_info,
            "owner_info": _get_user_basic_info(db, contract.owner_id),
            "creator_info": _get_user_basic_info(db, contract.creator_id),
            "status_info": _contract_status_info(contract.status),
        })

        result.append(ContractListResponse(**contract_dict))

    return result


@router.get("/{customer_id}/payment-plans", response_model=List[PaymentPlanResponse], summary="获取客户回款计划列表", description="""
获取指定客户的所有回款计划，支持按状态筛选和分页查询。

**功能说明：**
- 查询客户的所有回款计划
- 支持按回款状态筛选
- 支持分页查询
- 返回回款计划详细信息

**业务场景：**
- 查看客户的回款计划
- 了解客户的回款进度
- 客户详情页展示回款计划

**路径参数：**
- customer_id: 客户对外ID

**查询参数：**
- status: 回款状态筛选（可选）：PENDING待回款、OVERDUE已逾期、PARTIAL部分回款、COMPLETED已登记
- skip: 分页跳过记录数（默认0）
- limit: 每页记录数（默认20，最大100）

**返回字段：**
- 回款计划基本信息：ID、阶段名称、计划金额、计划日期等
- 已回款金额：paid_amount
- 待回款金额：remaining_amount
- 回款记录列表：payment_records
- 合同信息：contract_name
- 客户信息：customer_name、opportunity_name
""")
def get_customer_payment_plans(
    customer_id: str,
    status: Optional[str] = Query(None, description="回款状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.payment import PaymentPlanStatus

    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    internal_customer_id = customer.id
    
    status_map = {
        PaymentPlanStatus.PENDING: "待回款",
        PaymentPlanStatus.OVERDUE: "已逾期",
        PaymentPlanStatus.PARTIAL: "部分回款",
        PaymentPlanStatus.COMPLETED: "已登记"
    }
    
    from sqlalchemy import text
    
    plans_query = text("""
        SELECT
            p.*,
            c.contract_name AS contract_name,
            c.contract_number AS contract_number,
            c.customer_id AS customer_id,
            c.opportunity_id AS opportunity_id,
            o.opportunity_name AS opportunity_name,
            c.owner_id AS owner_id,
            c.creator_id AS creator_id
        FROM crm_contract_payment_plans p
        JOIN crm_contracts c ON p.contract_id = c.id
        LEFT JOIN crm_opportunities o ON c.opportunity_id = o.id
        WHERE c.customer_id = :customer_id
          AND p.team_id = :team_id
          AND c.team_id = :team_id
          AND c.deleted_at IS NULL
        ORDER BY p.due_date ASC, p.id DESC
    """)
    if status:
        plans_query = text("""
            SELECT
                p.*,
                c.contract_name AS contract_name,
                c.contract_number AS contract_number,
                c.customer_id AS customer_id,
                c.opportunity_id AS opportunity_id,
                o.opportunity_name AS opportunity_name,
                c.owner_id AS owner_id,
                c.creator_id AS creator_id
            FROM crm_contract_payment_plans p
            JOIN crm_contracts c ON p.contract_id = c.id
            LEFT JOIN crm_opportunities o ON c.opportunity_id = o.id
            WHERE c.customer_id = :customer_id
              AND p.team_id = :team_id
              AND c.team_id = :team_id
              AND c.deleted_at IS NULL
              AND p.status = :status
            ORDER BY p.due_date ASC, p.id DESC
        """)
    
    plans_result = db.execute(
        plans_query,
        {"customer_id": internal_customer_id, "team_id": team_id, "status": status}
    ).fetchall()
    
    plans = []
    for row in plans_result:
        plan_dict = dict(row._mapping)
        
        paid_amount = 0.0
        payment_records = []
        
        records_query = text("""
            SELECT * FROM crm_payment_records
            WHERE payment_plan_id = :plan_id
            ORDER BY payment_date DESC
        """)
        records_result = db.execute(records_query, {"plan_id": plan_dict['id']}).fetchall()
        
        for record_row in records_result:
            record_dict = dict(record_row._mapping)
            payment_records.append(record_dict)
            if record_dict.get('approval_phase') == 'approved':
                paid_amount += float(record_dict['actual_amount'])
        
        plan_dict['paid_amount'] = paid_amount
        plan_dict['remaining_amount'] = float(plan_dict['planned_amount']) - paid_amount
        plan_dict['payment_records'] = payment_records
        plan_dict['contract_name'] = plan_dict.get('contract_name')
        plan_dict['customer_id'] = customer.public_id
        plan_dict['customer_name'] = customer.account_name
        plan_dict['opportunity_name'] = plan_dict.get('opportunity_name')
        plan_dict['status_name'] = status_map.get(plan_dict['status'], plan_dict['status'])
        
        invoice_query = text("""
            SELECT COUNT(*) as count, COALESCE(SUM(invoice_amount), 0) as total_amount
            FROM crm_invoice_applications
            WHERE payment_plan_id = :plan_id AND status != 'DRAFT'
        """)
        invoice_result = db.execute(invoice_query, {"plan_id": plan_dict['id']}).first()
        plan_dict['is_invoiced'] = invoice_result.count > 0
        plan_dict['invoice_count'] = invoice_result.count
        plan_dict['invoiced_amount'] = float(invoice_result.total_amount) if invoice_result.total_amount else 0.0
        
        plans.append(plan_dict)
    
    if skip:
        plans = plans[skip:]
    if limit:
        plans = plans[:limit]
    
    return plans


@router.get("/{customer_id}/invoices", response_model=List[InvoiceApplicationResponse], summary="获取客户发票列表", description="""
获取指定客户的所有发票申请，支持按状态筛选和分页查询。

**功能说明：**
- 查询客户的所有发票申请
- 支持按发票状态筛选
- 支持分页查询
- 返回发票申请详细信息

**业务场景：**
- 查看客户的发票申请
- 了解客户的发票进度
- 客户详情页展示发票列表

**路径参数：**
- customer_id: 客户对外ID

**查询参数：**
- status: 发票状态筛选（可选）
- skip: 分页跳过记录数（默认0）
- limit: 每页记录数（默认20，最大100）

**返回字段：**
- 发票申请基本信息：ID、申请编号、发票类型、金额等
- 关联合同信息：contract_name、contract_number
- 回款计划信息：stage_name、planned_amount
- 申请人信息：applicant_name
- 审批状态：status、approval_status
""")
def get_customer_invoices(
    customer_id: str,
    status: Optional[str] = Query(None, description="发票状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    invoices, total = invoice_application_crud.list_applications(
        db=db,
        team_id=team_id,
        customer_id=customer.id,
        status=status,
        skip=skip,
        limit=limit
    )
    
    populated_invoices = []
    for invoice in invoices:
        if hasattr(invoice, 'contract') and invoice.contract:
            invoice.contract_name = invoice.contract.contract_name
            invoice.contract_number = invoice.contract.contract_number
        if hasattr(invoice, 'payment_plan') and invoice.payment_plan:
            invoice.stage_name = invoice.payment_plan.stage_name
            invoice.planned_amount = float(invoice.payment_plan.planned_amount)
        if hasattr(invoice, 'applicant') and invoice.applicant:
            invoice.applicant_name = invoice.applicant.name
        populated_invoices.append(_populate_application_info(db, invoice, team_id))
    
    return populated_invoices


@router.get("/{customer_id}/invoice-titles", response_model=List[InvoiceTitleResponse], summary="获取客户发票抬头列表", description="""
获取指定客户的所有发票抬头。

**功能说明：**
- 查询客户的所有发票抬头
- 默认抬头排在前面
- 返回抬头详细信息

**业务场景：**
- 查看客户的发票抬头
- 创建发票时选择抬头
- 客户详情页展示抬头列表

**路径参数：**
- customer_id: 客户对外ID

**返回字段：**
- 抬头基本信息：ID、抬头名称、纳税人识别号
- 抬头类型：COMPANY(单位)、PERSONAL(个人)
- 账户信息：开户行、开户账号
- 联系信息：地址、电话
- 默认标识：is_default
""")
def get_customer_invoice_titles(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    invoice_titles = invoice_title_crud.get_by_customer_id(db, customer.id, team_id)
    return [_invoice_title_response(db, invoice_title, team_id) for invoice_title in invoice_titles]


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, summary="创建客户", description="手动创建客户，AI自动生成档案")
async def create_customer(
    customer: CustomerCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    _ensure_customer_name_available(db, customer.account_name, team_id)

    new_customer = customer_crud.create(
        db=db,
        obj_in=customer,
        creator_id=str(current_user.id),
        team_id=team_id,
        operator_name=current_user.name
    )
    if customer.primary_contact:
        contact_crud.create(
            db=db,
            obj_in=customer.primary_contact,
            customer_id=new_customer.id,
            team_id=team_id,
            is_primary=True
        )

    # 设置档案状态为 PENDING
    customer_crud.update_profile_status(db, new_customer.id, "PENDING")

    # 触发客户智能档案生成（异步，进入 LangGraph 统一编排）
    await customer_intelligence_refresh_service.trigger_customer_created_refresh(
        db,
        team_id=team_id,
        customer_id=new_customer.id,
        actor_id=str(current_user.id),
        source_lead_id=None,
    )

    return _customer_response(db, new_customer)


@router.get("/", response_model=PaginatedResponse[CustomerListResponse], summary="查询客户列表", description="支持分页、按客户名称/行业/城市/状态/负责人等多条件筛选，支持动态排序，返回负责人和创建人信息")
def get_customers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    customer_status: Optional[str] = Query(None, alias="status", description="客户状态，多个值用逗号分隔"),
    status_exclude: Optional[str] = Query(None, description="排除的客户状态，多个值用逗号分隔"),
    industry: str = Query(None, description="所属行业"),
    industry_exclude: Optional[str] = Query(None, description="排除的所属行业，多个值用逗号分隔"),
    city: str = Query(None, description="所在城市"),
    source: str = Query(None, description="客户来源"),
    source_exclude: Optional[str] = Query(None, description="排除的客户来源，多个值用逗号分隔"),
    company_scale: str = Query(None, description="公司规模"),
    company_scale_exclude: Optional[str] = Query(None, description="排除的公司规模，多个值用逗号分隔"),
    owner_id: str = Query(None, description="负责人ID（支持 'me' 表示当前用户）"),
    owner_id_exclude: Optional[str] = Query(None, description="排除的负责人ID，多个值用逗号分隔"),
    keyword: str = Query(None, description="关键词搜索"),
    created_time_start: Optional[date] = Query(None, description="创建时间起始"),
    created_time_end: Optional[date] = Query(None, description="创建时间结束"),
    order_by: str = Query(None, description="排序字段（created_time/account_name/city/status/industry）"),
    order_dir: str = Query(None, description="排序方向（asc/desc）"),
    scope: Optional[str] = Query(None, description="客户范围：collaborated/accessible"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.permission import permission_crud

    # 获取用户权限码
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有 view:all 权限
    has_view_all = "customer:view:all" in permission_codes

    actual_owner_id = owner_id
    if owner_id in ["me", "my"]:
        actual_owner_id = str(current_user.id)

    requested_owner_ids = [item.strip() for item in actual_owner_id.split(",") if item.strip()] if actual_owner_id else []

    # 权限验证：如果指定了其他人的 owner_id，必须有 view:all 权限
    if requested_owner_ids and any(item != str(current_user.id) for item in requested_owner_ids):
        if not has_view_all:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能查看自己负责的客户，或需要 customer:view:all 权限查看他人数据"
            )

    allowed_scopes = {None, "collaborated", "accessible"}
    if scope not in allowed_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope 仅支持 collaborated/accessible"
        )

    current_user_id = str(current_user.id)
    include_collaborated = False
    if scope == "collaborated":
        actual_owner_id = None
    elif scope == "accessible" and not has_view_all:
        actual_owner_id = None
        include_collaborated = True
    elif actual_owner_id is None and not has_view_all:
        actual_owner_id = current_user_id

    customers, total = customer_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        status=customer_status,
        status_exclude=status_exclude,
        industry=industry,
        industry_exclude=industry_exclude,
        city=city,
        source=source,
        source_exclude=source_exclude,
        company_scale=company_scale,
        company_scale_exclude=company_scale_exclude,
        owner_id=actual_owner_id,
        owner_id_exclude=owner_id_exclude,
        keyword=keyword,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        order_by=order_by,
        order_dir=order_dir,
        scope=scope,
        current_user_id=current_user_id,
        include_collaborated=include_collaborated
    )
    
    result = []
    owner_ids = set(c.owner_id for c in customers if c.owner_id)
    creator_ids = set(c.creator_id for c in customers if c.creator_id)
    customer_ids = [c.id for c in customers]
    source_lead_ids = [c.source_lead_id for c in customers if c.source_lead_id]
    procurement_method_ids = set(c.default_procurement_method_id for c in customers if c.default_procurement_method_id)
    
    users_info = {}
    if owner_ids or creator_ids:
        all_user_ids = owner_ids.union(creator_ids)
        if all_user_ids:
            placeholders = ','.join(':user_id_' + str(i) for i in range(len(all_user_ids)))
            users_query = text(f"""
                SELECT id, name, avatar_url
                FROM users
                WHERE id IN ({placeholders})
            """)

            params = {f'user_id_{i}': int(user_id) for i, user_id in enumerate(all_user_ids)}
            users_result = db.execute(users_query, params).fetchall()

            for row in users_result:
                users_info[str(row[0])] = {
                    'id': str(row[0]),
                    'name': row[1],
                    'avatar_url': row[2]
                }

    collaborator_user_ids = set()
    collaborator_member_rows = []
    if customer_ids:
        placeholders = ','.join(':customer_id_' + str(i) for i in range(len(customer_ids)))
        collaborators_query = text(f"""
            SELECT customer_id, user_id
            FROM crm_customer_members cm
            WHERE cm.team_id = :team_id
              AND cm.customer_id IN ({placeholders})
              AND cm.is_active = TRUE
            ORDER BY cm.created_time ASC, cm.id ASC
        """)
        params = {'team_id': team_id}
        params.update({f'customer_id_{i}': customer_id for i, customer_id in enumerate(customer_ids)})
        collaborator_member_rows = db.execute(collaborators_query, params).fetchall()

        collaborator_user_ids = {str(row[1]) for row in collaborator_member_rows if str(row[1]).isdigit()}

    collaborator_users_info = {}
    if collaborator_user_ids:
        placeholders = ','.join(':user_id_' + str(i) for i in range(len(collaborator_user_ids)))
        users_query = text(f"""
            SELECT id, name, avatar_url
            FROM users
            WHERE id IN ({placeholders})
        """)
        params = {f'user_id_{i}': int(user_id) for i, user_id in enumerate(collaborator_user_ids)}
        users_result = db.execute(users_query, params).fetchall()

        for row in users_result:
            collaborator_users_info[str(row[0])] = {
                'id': str(row[0]),
                'name': row[1],
                'avatar_url': row[2]
            }

    collaborators_by_customer = {}
    for customer_id, user_id in collaborator_member_rows:
        user_info = collaborator_users_info.get(str(user_id))
        if user_info:
            collaborators_by_customer.setdefault(customer_id, []).append(user_info)

    source_lead_public_ids = {}
    if source_lead_ids:
        placeholders = ','.join(':lead_id_' + str(i) for i in range(len(source_lead_ids)))
        source_leads_query = text(f"""
            SELECT id, public_id
            FROM crm_leads
            WHERE id IN ({placeholders})
        """)
        params = {f'lead_id_{i}': lead_id for i, lead_id in enumerate(source_lead_ids)}
        source_leads_result = db.execute(source_leads_query, params).fetchall()
        source_lead_public_ids = {row[0]: row[1] for row in source_leads_result}
    
    procurement_methods_info = {}
    if procurement_method_ids:
        from app.models.procurement import ProcurementMethod
        methods = db.query(ProcurementMethod).filter(
            ProcurementMethod.id.in_(procurement_method_ids)
        ).all()
        for m in methods:
            procurement_methods_info[m.id] = {
                'id': m.id,
                'code': m.code,
                'name': m.name,
                'is_active': m.is_active
            }
    
    industries_info = {}
    industry_values = set()
    for customer in customers:
        if customer.industry:
            industry_values.add(customer.industry)

    # 批量查询所有行业信息（含父行业）
    if industry_values:
        from app.crud.industry import industry_crud

        industries_map = industry_crud.get_by_codes_with_parent(db, list(industry_values))
        for industry_code, industry in industries_map.items():
            # 构建完整路径：一级行业/二级行业
            if industry.level == 2 and industry.parent:
                full_name = f"{industry.parent.name}/{industry.name}"
                parent_code = industry.parent.code
            else:
                full_name = industry.name
                parent_code = None

            industries_info[industry_code] = {
                'code': industry.code,
                'name': full_name,
                'primary_code': parent_code,
                'primary_name': industry.parent.name if industry.parent else None,
                'secondary_name': industry.name if industry.level == 2 else None
            }
    
    for customer in customers:
        customer_dict = {
            'id': customer.public_id,
            'public_id': customer.public_id,
            'account_name': customer.account_name,
            'industry': customer.industry,
            'industry_info': industries_info.get(customer.industry),
            'city': customer.city,
            'address': customer.address,
            'company_scale': customer.company_scale,
            'source': customer.source,
            'status': customer.status,
            'owner_id': customer.owner_id,
            'source_lead_id': source_lead_public_ids.get(customer.source_lead_id),
            'default_procurement_method_id': customer.default_procurement_method_id,
            'return_reason': customer.return_reason,
            'returned_time': customer.returned_time,
            'creator_id': customer.creator_id,
            'created_time': customer.created_time,
            'last_modified_time': customer.last_modified_time,
            'version': customer.version,
            'license_expiry_date': customer.license_expiry_date,
            'license_type': customer.license_type,
            'owner_info': users_info.get(customer.owner_id) if customer.owner_id else None,
            'collaborator_infos': collaborators_by_customer.get(customer.id, []),
            'creator_info': users_info.get(customer.creator_id) if customer.creator_id else None,
            'default_procurement_method_info': procurement_methods_info.get(customer.default_procurement_method_id) if customer.default_procurement_method_id else None
        }
        result.append(CustomerListResponse(**customer_dict))
    
    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[CustomerListResponse](
        items=result,
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


def _can_manage_customer_members(db: Session, customer, team_id: int, current_user) -> bool:
    from app.crud.permission import permission_crud
    from app.crud.role import role_crud

    if customer.owner_id == str(current_user.id):
        return True

    permission_codes = {p.code for p in permission_crud.get_user_permissions(db, current_user.id, team_id)}
    if "customer:assign" in permission_codes or "customer:edit:all" in permission_codes:
        return True

    role_codes = {r.code for r in role_crud.get_user_roles(db, current_user.id, team_id)}
    return "TEAM_ADMIN" in role_codes


def _build_customer_member_response(db: Session, member, customer_public_id: str, can_manage: bool) -> CustomerMemberResponse:
    user_info = None
    if member.user_id:
        row = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :user_id
        """), {"user_id": int(member.user_id)}).first()
        if row:
            user_info = CustomerMemberUserInfo(
                id=str(row[0]),
                name=row[1],
                avatar_url=row[2],
            )

    return CustomerMemberResponse(
        id=member.id,
        customer_id=customer_public_id,
        user_id=member.user_id,
        member_role=member.member_role,
        access_level=member.access_level,
        remark=member.remark,
        created_by=member.created_by,
        created_time=member.created_time,
        updated_time=member.updated_time,
        user_info=user_info,
        can_manage=can_manage,
    )


@router.get("/{customer_id}/members", response_model=List[CustomerMemberResponse], summary="查询客户团队成员")
def get_customer_members(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    can_manage = _can_manage_customer_members(db, customer, team_id, current_user)
    members = customer_member_crud.get_by_customer(db, team_id, customer.id)
    return [_build_customer_member_response(db, member, customer.public_id, can_manage) for member in members]


@router.get("/{customer_id}/member-candidates", response_model=List[CustomerMemberCandidate], summary="查询客户团队成员候选人")
def get_customer_member_candidates(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    return customer_member_crud.get_candidates(db, team_id, customer.id)


@router.post("/{customer_id}/members", response_model=CustomerMemberResponse, status_code=status.HTTP_201_CREATED, summary="添加客户团队成员")
def add_customer_member(
    customer_id: str,
    member_in: CustomerMemberCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    if customer.owner_id == str(member_in.user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="客户负责人无需添加为团队成员"
        )
    if not team_crud.is_member(db, team_id, int(member_in.user_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能添加当前团队成员"
        )

    member = customer_member_crud.create_or_restore(
        db=db,
        team_id=team_id,
        customer_id=customer.id,
        obj_in=member_in,
        created_by=str(current_user.id),
    )
    return _build_customer_member_response(db, member, customer.public_id, True)


@router.put("/{customer_id}/members/{member_id}", response_model=CustomerMemberResponse, summary="更新客户团队成员")
def update_customer_member(
    customer_id: str,
    member_id: int,
    member_in: CustomerMemberUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    member = customer_member_crud.get_by_id(db, member_id, team_id)
    if not member or member.customer_id != customer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户团队成员不存在"
        )
    updated = customer_member_crud.update(db, member, member_in)
    return _build_customer_member_response(db, updated, customer.public_id, True)


@router.delete("/{customer_id}/members/{member_id}", response_model=MessageResponse, summary="移除客户团队成员")
def remove_customer_member(
    customer_id: str,
    member_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    member = customer_member_crud.get_by_id(db, member_id, team_id)
    if not member or member.customer_id != customer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户团队成员不存在"
        )
    customer_member_crud.deactivate(db, member)
    return MessageResponse(message="移除成功")


@router.get("/{customer_id}", response_model=CustomerDetailResponse, summary="获取客户详情", description="返回客户信息及其所有联系人列表")
def get_customer(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    contacts = contact_crud.get_by_customer_id(db, customer.id, team_id)
    
    owner_info = None
    if customer.owner_id:
        from app.crud.user import user_crud
        owner = user_crud.get_by_id(db, int(customer.owner_id))
        if owner:
            owner_info = {
                'id': str(owner.id),
                'name': owner.name,
                'avatar_url': owner.avatar_url
            }
    
    creator_info = None
    if customer.creator_id:
        from app.crud.user import user_crud
        creator = user_crud.get_by_id(db, int(customer.creator_id))
        if creator:
            creator_info = {
                'id': str(creator.id),
                'name': creator.name,
                'avatar_url': creator.avatar_url
            }
    
    procurement_method_info = None
    if customer.default_procurement_method_id:
        from app.crud.procurement import procurement_method_crud
        procurement_method = procurement_method_crud.get(db, customer.default_procurement_method_id)
        if procurement_method:
            procurement_method_info = {
                'id': procurement_method.id,
                'code': procurement_method.code,
                'name': procurement_method.name,
                'is_active': procurement_method.is_active
            }
    
    industry_info = None
    if customer.industry:
        from app.crud.industry import industry_crud

        # 从 crm_industries 表获取行业信息（含父行业）
        industry = industry_crud.get_by_code_with_parent(db, customer.industry)
        if industry:
            # 构建完整路径：一级行业/二级行业
            if industry.level == 2 and industry.parent:
                full_name = f"{industry.parent.name}/{industry.name}"
                parent_code = industry.parent.code
            else:
                full_name = industry.name
                parent_code = None

            industry_info = {
                'code': industry.code,
                'name': full_name,
                'primary_code': parent_code,
                'primary_name': industry.parent.name if industry.parent else None,
                'secondary_name': industry.name if industry.level == 2 else None
            }
    
    customer_payload = {
        **customer.__dict__,
        "id": customer.public_id,
        "public_id": customer.public_id,
        "source_lead_id": source_lead.public_id if (source_lead := lead_crud.get_by_id(db, customer.source_lead_id, team_id)) else None,
        "customer_brief_markdown": industry_display_service.sanitize_markdown(
            db,
            customer.customer_brief_markdown,
            industry_code=customer.industry,
        ),
    }

    return CustomerDetailResponse(
        **customer_payload,
        contacts=[_contact_response(contact, customer.public_id) for contact in contacts],
        owner_info=owner_info,
        creator_info=creator_info,
        default_procurement_method_info=procurement_method_info,
        industry_info=industry_info,
        customer_intelligence_has_inputs=customer_intelligence_refresh_service.has_customer_business_data(
            db,
            customer_id=customer.id,
            team_id=team_id,
        ),
    )


@router.put("/{customer_id}", response_model=CustomerResponse, summary="编辑客户", description="更新客户信息")
def update_customer(
    customer_id: str,
    customer_update: CustomerUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    if customer_update.account_name:
        _ensure_customer_name_available(db, customer_update.account_name, team_id, exclude_customer_id=customer.id)

    return _customer_response(db, customer_crud.update(db, customer, customer_update))


@router.patch("/{customer_id}/status", response_model=CustomerResponse, summary="更新客户状态", description="用于标记赢单、输单等关键状态变更")
async def update_customer_status(
    customer_id: str,
    status_update: CustomerStatusUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.feishu import feishu_service

    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    new_status = status_update.status
    updated_customer = customer_crud.update_status(db, customer, new_status)

    if new_status == 1:
        await feishu_service.notify_account_status_won(
            customer.owner_id,
            customer.account_name
        )
    elif new_status == 2:
        await feishu_service.notify_account_status_lost(
            customer.owner_id,
            customer.account_name
        )

    return _customer_response(db, updated_customer)


@router.patch("/{customer_id}/lose", response_model=CustomerResponse, summary="标记输单", description="将客户标记为输单，必须记录输单原因")
async def mark_customer_as_lost(
    customer_id: str,
    lose_data: CustomerLoseRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.feishu import feishu_service

    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    if customer.status == 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该客户已标记为输单"
        )

    updated_customer = customer_crud.mark_as_lost(
        db, customer, lose_data.loss_reason, str(current_user.id), current_user.name
    )

    await feishu_service.notify_account_status_lost(
        customer.owner_id,
        customer.account_name
    )

    return _customer_response(db, updated_customer)


@router.delete("/{customer_id}", response_model=MessageResponse, summary="删除客户", description="逻辑删除，需校验权限")
def delete_customer(
    customer_id: str,
    customer = Depends(check_customer_delete_permission),
    db: Session = Depends(get_db)
):
    try:
        customer_crud.delete(db, customer, str(customer.owner_id) if customer.owner_id else None)
        return MessageResponse(message="删除成功")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{customer_id}/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED, summary="添加联系人", description="为指定客户添加新联系人")
async def create_contact(
    customer_id: str,
    contact: ContactCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    created_contact = contact_crud.create(db, contact, customer.id, team_id)
    await _schedule_contact_intelligence_refresh(
        db,
        created_contact,
        trigger_type="customer_contact_created",
        actor_id=str(current_user.id),
    )
    return _contact_response(created_contact, customer.public_id)


@router.get("/{customer_id}/contacts", response_model=List[ContactResponse], summary="查询联系人列表", description="获取指定客户下的全部联系人")
def get_contacts(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    return [_contact_response(contact, customer.public_id) for contact in contact_crud.get_by_customer_id(db, customer.id, team_id)]


@router.put("/contacts/{contact_id}", response_model=ContactResponse, summary="编辑联系人", description="更新联系人信息")
async def update_contact(
    contact_id: int,
    contact_update: ContactUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contact = contact_crud.get_by_id(db, contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )
    customer = _get_editable_customer(db, contact.customer_id, team_id, current_user)

    updated_contact = contact_crud.update(db, contact, contact_update)
    await _schedule_contact_intelligence_refresh(
        db,
        updated_contact,
        trigger_type="customer_contact_updated",
        actor_id=str(current_user.id),
    )
    return _contact_response(updated_contact, customer.public_id)


@router.patch("/contacts/{contact_id}/set-primary", response_model=ContactResponse, summary="设置主联系人", description="设置某联系人为主联系人")
async def set_primary_contact(
    contact_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contact = contact_crud.get_by_id(db, contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )
    customer = _get_editable_customer(db, contact.customer_id, team_id, current_user)

    updated_contact = contact_crud.set_primary(db, contact, team_id)
    await _schedule_contact_intelligence_refresh(
        db,
        updated_contact,
        trigger_type="customer_contact_updated",
        actor_id=str(current_user.id),
    )
    return _contact_response(updated_contact, customer.public_id)


@router.delete("/contacts/{contact_id}", response_model=MessageResponse, summary="删除联系人", description="删除联系人")
async def delete_contact(
    contact_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contact = contact_crud.get_by_id(db, contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )
    _get_editable_customer(db, contact.customer_id, team_id, current_user)

    from app.services.customer_intelligence_event_service import customer_intelligence_event_service

    deleted_event = customer_intelligence_event_service.from_contact(
        contact,
        trigger_type="customer_contact_deleted",
        actor_id=str(current_user.id),
    )
    try:
        contact_crud.delete(db, contact)
        if deleted_event is not None:
            await _schedule_customer_intelligence_event_refresh(db, deleted_event)
        return MessageResponse(message="删除成功")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/statistics/summary", response_model=StatisticsResponse, summary="查询统计", description="查询客户统计数据")
def get_statistics(
    owner_id: str = Query(None, description="负责人ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return StatisticsResponse(**customer_crud.get_statistics(db, team_id, owner_id))


@router.get("/statistics/trend", response_model=List[TrendResponse], summary="查询趋势", description="查询客户创建趋势")
def get_trend(
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    owner_id: str = Query(None, description="负责人ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    trend_data = customer_crud.get_trend(db, team_id, days, owner_id)
    return [TrendResponse(**item) for item in trend_data]


@router.post("/{customer_id}/return-to-pool", response_model=CustomerReturnResponse, summary="客户退回公海", description="将客户退回到公海池，解除与负责人的绑定")
async def return_customer_to_pool(
    customer_id: str,
    return_data: CustomerReturnRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.role import role_crud

    customer = _get_customer_or_404(db, customer_id, team_id)

    if customer.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该客户已在公海池中"
        )

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    is_admin = "TEAM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes

    if not (is_admin or is_director or customer.owner_id == str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限操作此客户"
        )

    previous_owner = customer.owner_id

    updated_customer = customer_crud.return_to_pool(
        db, customer, return_data.return_reason, team_id, return_data.detailed_reason
    )

    from app.services.feishu import feishu_service
    try:
        await feishu_service.send_customer_returned_notification(
            customer.account_name,
            return_data.return_reason,
            previous_owner
        )
    except Exception as e:
        print(f"飞书通知发送失败: {e}")

    return CustomerReturnResponse(
        customer_id=updated_customer.public_id,
        previous_owner=previous_owner,
        returned_time=updated_customer.returned_time,
        return_reason=updated_customer.return_reason,
        message="客户已成功退回公海"
    )


@router.get("/public/list", response_model=PaginatedResponse[CustomerResponse], summary="查询公海客户", description="获取公海池中的客户列表，支持动态排序")
def get_public_customers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    status: Optional[int] = Query(None, description="客户状态"),
    city: Optional[str] = Query(None, description="所在城市"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    order_by: Optional[str] = Query(None, description="排序字段"),
    order_dir: Optional[str] = Query(None, description="排序方向（asc/desc）"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customers, total = customer_crud.get_public_customers(
        db, team_id=team_id, skip=skip, limit=limit,
        status=status, city=city, keyword=keyword,
        order_by=order_by, order_dir=order_dir
    )
    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[CustomerResponse](
        items=[_customer_response(db, customer) for customer in customers],
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


@router.post("/{customer_id}/claim", response_model=CustomerResponse, summary="领取客户", description="从公海池中领取客户")
def claim_customer(
    customer_id: str,
    claim_data: CustomerClaimRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_customer_or_404(db, customer_id, team_id)

    try:
        updated_customer = customer_crud.claim_customer(
            db, customer, claim_data.owner_id, team_id
        )
        return _customer_response(db, updated_customer)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{customer_id}/assign", response_model=CustomerAssignResponse, summary="移交客户", description="有 customer:assign 权限的用户可移交客户，并可选择同步移交关联商机及其合同")
def assign_customer(
    customer_id: str,
    assign_data: CustomerAssignRequest,
    team_id: int = Depends(get_current_user_team),
    _current_user = Depends(require_permission("customer:assign")),
    db: Session = Depends(get_db)
):
    try:
        target_user_id = int(assign_data.owner_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目标负责人ID无效"
        )

    target_user = user_crud.get_by_id(db, target_user_id)
    if not target_user or not team_crud.is_member(db, team_id, target_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目标负责人不存在或不属于当前团队"
        )

    customer = _get_customer_or_404(db, customer_id, team_id)

    try:
        updated_customer, transferred_opportunities, transferred_contracts = customer_crud.assign_customer(
            db,
            customer,
            assign_data.owner_id,
            team_id,
            assign_data.opportunity_transfer_scope
        )
        return CustomerAssignResponse(
            customer=updated_customer,
            transferred_opportunities=transferred_opportunities,
            transferred_contracts=transferred_contracts,
            message="客户已移交"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{customer_id}/regenerate-brief", response_model=MessageResponse, summary="重新生成客户概况", description="AI重新生成销售侧客户概况")
async def regenerate_customer_brief(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    await customer_intelligence_refresh_service.trigger_manual_refresh(
        db,
        team_id=team_id,
        customer_id=customer.id,
        actor_id=str(current_user.id),
        scope="brief",
    )

    return MessageResponse(message="客户概况正在生成")


@router.post(
    "/{customer_id}/regenerate-intelligence",
    response_model=MessageResponse,
    summary="重新生成客户智能档案",
    description="AI重新生成客户档案和客户概况",
)
async def regenerate_customer_intelligence(
    customer_id: str,
    payload: CustomerIntelligenceRegenerateRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    await customer_intelligence_refresh_service.trigger_manual_refresh(
        db,
        team_id=team_id,
        customer_id=customer.id,
        actor_id=str(current_user.id),
        scope=payload.scope,
    )

    return MessageResponse(message="客户智能档案正在生成")


@router.post(
    "/intelligence/batch-rebuild",
    response_model=CustomerIntelligenceBatchRebuildResponse,
    summary="批量重建客户智能档案",
    description="通过客户智能 LangGraph 运行时批量重建客户档案/客户概况",
)
async def rebuild_customer_intelligence_batch(
    payload: CustomerIntelligenceBatchRebuildRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    customer_ids = None
    if payload.customer_ids is not None:
        customers = [
            _get_customer_or_404(db, customer_public_id, team_id)
            for customer_public_id in payload.customer_ids
        ]
        customer_ids = [customer.id for customer in customers]

    result = await customer_intelligence_refresh_service.trigger_batch_rebuild(
        db,
        team_id=team_id,
        actor_id=str(current_user.id),
        scope=payload.scope,
        customer_ids=customer_ids,
        limit=payload.limit,
    )
    result_customers = [
        customer_crud.get_by_id(db, customer_id, team_id)
        for customer_id in result.customer_ids
    ]
    return CustomerIntelligenceBatchRebuildResponse(
        message="客户智能档案批量重建已开始",
        request_id=result.request_id,
        scope=result.scope,
        total=result.total,
        scheduled=result.scheduled,
        customer_ids=[customer.public_id for customer in result_customers if customer],
    )


@router.get(
    "/intelligence/runs",
    response_model=CustomerIntelligenceRunDiagnosticListResponse,
    summary="查询客户智能运行诊断",
    description="查询客户智能 LangGraph 运行审计和用户可见执行轨迹",
)
def list_customer_intelligence_runs(
    customer_id: Optional[str] = Query(None, description="客户对外ID"),
    request_id: Optional[str] = Query(None, min_length=1, max_length=120, description="请求ID"),
    run_status: Optional[str] = Query(None, alias="status", min_length=1, max_length=30, description="运行状态"),
    limit: int = Query(20, ge=1, le=100, description="返回记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_run_service import customer_intelligence_run_service

    customer = _get_customer_or_404(db, customer_id, team_id) if customer_id else None
    diagnostics = customer_intelligence_run_service.list_diagnostics(
        db,
        team_id=team_id,
        customer_id=customer.id if customer else None,
        request_id=request_id,
        status=run_status,
        limit=limit,
    )
    return CustomerIntelligenceRunDiagnosticListResponse(
        items=[_customer_intelligence_run_response(db, team_id, diagnostic) for diagnostic in diagnostics],
        total=len(diagnostics),
        limit=limit,
    )


@router.get(
    "/intelligence/runs/{run_id}",
    response_model=CustomerIntelligenceRunDiagnosticResponse,
    summary="查询客户智能运行详情",
    description="查询单次客户智能 LangGraph 运行审计和可回放执行轨迹",
)
def get_customer_intelligence_run(
    run_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_run_service import customer_intelligence_run_service

    diagnostic = customer_intelligence_run_service.get_diagnostic(
        db,
        team_id=team_id,
        run_id=run_id,
    )
    if diagnostic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户智能运行记录不存在",
        )
    return _customer_intelligence_run_response(db, team_id, diagnostic)


@router.post(
    "/intelligence/retries/run-due",
    response_model=CustomerIntelligenceRetryDueResponse,
    summary="执行到期客户智能重试",
    description="调度已到重试时间的客户智能 LangGraph 运行",
)
async def run_due_customer_intelligence_retries(
    limit: int = Query(20, ge=1, le=100, description="本次最多处理数量"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    result = await customer_intelligence_refresh_service.run_due_retries(team_id=team_id, limit=limit)
    return CustomerIntelligenceRetryDueResponse(
        success=result.get("success") is True,
        total=int(result.get("total") or 0),
        succeeded=int(result.get("succeeded") or 0),
        failed=int(result.get("failed") or 0),
        results=[
            item
            for item in result.get("results", [])
            if isinstance(item, dict)
        ],
    )
