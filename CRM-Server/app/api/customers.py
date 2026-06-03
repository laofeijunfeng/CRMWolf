from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_permission, get_current_user_team, check_customer_delete_permission
from app.crud.customer import customer_crud, contact_crud
from app.crud.user import user_crud
from app.crud.contract import contract_crud
from app.crud.payment import payment_plan_crud
from app.crud.invoice import invoice_application_crud, invoice_title_crud
from app.schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerStatusUpdate,
    CustomerResponse, CustomerDetailResponse, CustomerListResponse,
    ConvertLeadToCustomer, ConvertResponse,
    ContactCreate, ContactUpdate, ContactResponse,
    MessageResponse, StatisticsResponse, TrendResponse,
    CustomerStatusEnum, CustomerReturnRequest, CustomerReturnResponse,
    ReturnReasonEnum, CustomerClaimRequest, CustomerAssignRequest,
    CustomerIndustryOption, CustomerLoseRequest
)
from app.schemas.contract import ContractListResponse
from app.schemas.payment import PaymentPlanResponse
from app.schemas.invoice import InvoiceApplicationResponse, InvoiceTitleResponse


router = APIRouter(prefix="/api/v1/customers", tags=["客户管理"])


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
    from app.services.feishu import feishu_service
    from app.services.customer_profile_service import customer_profile_service

    try:
        customer, contact = customer_crud.convert_from_lead(
            db=db,
            lead_id=data.lead_id,
            account_name=data.account_name,
            address=data.address,
            default_procurement_method_id=data.default_procurement_method_id,
            creator_id=str(current_user.id),
            operator_name=current_user.name,
            team_id=team_id
        )

        # 设置档案状态为 PENDING
        customer_crud.update_profile_status(db, customer.id, "PENDING")

        # 触发档案生成（异步，包含线索跟进记录分析）
        await customer_profile_service.trigger_generation(
            customer_id=customer.id,
            account_name=customer.account_name,
            source_lead_id=data.lead_id,
            team_id=team_id
        )

        await feishu_service.notify_account_created(
            customer.owner_id,
            customer.account_name,
            contact.name
        )

        return ConvertResponse(
            customer_id=customer.id,
            contact_id=contact.id,
            message="转化成功，AI正在生成客户档案"
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
- customer_id: 客户ID

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
    customer_id: int,
    status: Optional[str] = Query(None, description="合同状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.contract import ContractStatus

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    contracts, total = contract_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        customer_id=customer_id,
        status=ContractStatus[status] if status else None
    )
    
    for contract in contracts:
        if hasattr(contract, 'customer') and contract.customer:
            contract.customer_name = contract.customer.account_name
        if hasattr(contract, 'opportunity') and contract.opportunity:
            contract.opportunity_name = contract.opportunity.opportunity_name
        if hasattr(contract, 'creator') and contract.creator:
            contract.creator_name = contract.creator.name
        
        from app.schemas.contract import ContractStatusEnum
        status_info = None
        if contract.status:
            try:
                status_enum = ContractStatusEnum(contract.status)
                status_info = {
                    "code": status_enum.value,
                    "name": status_enum.description
                }
            except ValueError:
                pass
        
        contract.status_info = status_info
    
    return contracts


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
- customer_id: 客户ID

**查询参数：**
- status: 回款状态筛选（可选）：PENDING待回款、OVERDUE已逾期、PARTIAL部分回款、COMPLETED已完成
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
    customer_id: int,
    status: Optional[str] = Query(None, description="回款状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.payment import PaymentPlanStatus

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在或不属于当前团队"
        )
    
    from app.models.payment import PaymentPlanStatus
    
    status_map = {
        PaymentPlanStatus.PENDING: "待回款",
        PaymentPlanStatus.OVERDUE: "已逾期",
        PaymentPlanStatus.PARTIAL: "部分回款",
        PaymentPlanStatus.COMPLETED: "已完成"
    }
    
    from sqlalchemy import text
    
    contracts_query = text("""
        SELECT id FROM crm_contracts
        WHERE customer_id = :customer_id
    """)
    contract_ids_result = db.execute(contracts_query, {"customer_id": customer_id}).fetchall()
    contract_ids = [row[0] for row in contract_ids_result] if contract_ids_result else []
    
    if not contract_ids:
        return []
    
    plans_query = text("""
        SELECT * FROM crm_contract_payment_plans
        WHERE contract_id IN :contract_ids
    """)
    if status:
        plans_query = text("""
            SELECT * FROM crm_contract_payment_plans
            WHERE contract_id IN :contract_ids AND status = :status
        """)
    
    plans_result = db.execute(
        plans_query,
        {"contract_ids": tuple(contract_ids), "status": status}
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
            paid_amount += float(record_dict['actual_amount'])
        
        plan_dict['paid_amount'] = paid_amount
        plan_dict['remaining_amount'] = float(plan_dict['planned_amount']) - paid_amount
        plan_dict['payment_records'] = payment_records
        plan_dict['contract_name'] = None
        plan_dict['customer_name'] = customer.account_name
        plan_dict['opportunity_name'] = None
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
- customer_id: 客户ID

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
    customer_id: int,
    status: Optional[str] = Query(None, description="发票状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    invoices, total = invoice_application_crud.list_applications(
        db=db,
        team_id=team_id,
        customer_id=customer_id,
        status=status,
        skip=skip,
        limit=limit
    )
    
    for invoice in invoices:
        if hasattr(invoice, 'contract') and invoice.contract:
            invoice.contract_name = invoice.contract.contract_name
            invoice.contract_number = invoice.contract.contract_number
        if hasattr(invoice, 'payment_plan') and invoice.payment_plan:
            invoice.stage_name = invoice.payment_plan.stage_name
            invoice.planned_amount = float(invoice.payment_plan.planned_amount)
        if hasattr(invoice, 'applicant') and invoice.applicant:
            invoice.applicant_name = invoice.applicant.name
    
    return invoices


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
- customer_id: 客户ID

**返回字段：**
- 抬头基本信息：ID、抬头名称、纳税人识别号
- 抬头类型：COMPANY(单位)、PERSONAL(个人)
- 账户信息：开户行、开户账号
- 联系信息：地址、电话
- 默认标识：is_default
""")
def get_customer_invoice_titles(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    invoice_titles = invoice_title_crud.get_by_customer_id(db, customer_id, team_id)
    return invoice_titles


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, summary="创建客户", description="手动创建客户，AI自动生成档案")
async def create_customer(
    customer: CustomerCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.customer_profile_service import customer_profile_service

    existing_customer = customer_crud.get_by_name(db, customer.account_name, team_id)
    if existing_customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="客户名称已存在"
        )

    new_customer = customer_crud.create(db, customer, str(current_user.id), current_user.name, team_id)

    # 设置档案状态为 PENDING
    customer_crud.update_profile_status(db, new_customer.id, "PENDING")

    # 触发档案生成（异步）
    await customer_profile_service.trigger_generation(
        customer_id=new_customer.id,
        account_name=new_customer.account_name,
        source_lead_id=None,
        team_id=team_id
    )

    return new_customer


@router.get("/", response_model=List[CustomerListResponse], summary="查询客户列表", description="支持分页、按客户名称/行业/城市/状态/负责人等多条件筛选，支持动态排序，返回负责人和创建人信息")
def get_customers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    status: CustomerStatusEnum = Query(None, description="客户状态"),
    industry: str = Query(None, description="所属行业"),
    city: str = Query(None, description="所在城市"),
    owner_id: str = Query(None, description="负责人ID（支持 'me' 表示当前用户）"),
    keyword: str = Query(None, description="关键词搜索"),
    order_by: str = Query(None, description="排序字段（created_time/account_name/city/status/industry）"),
    order_dir: str = Query(None, description="排序方向（asc/desc）"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.role import role_crud

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    is_admin = "TEAM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes

    actual_owner_id = owner_id
    if owner_id in ["me", "my"]:
        actual_owner_id = str(current_user.id)

    customers, _ = customer_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        status=int(status) if status else None,
        industry=industry,
        city=city,
        owner_id=actual_owner_id,
        keyword=keyword,
        order_by=order_by,
        order_dir=order_dir
    )
    
    result = []
    owner_ids = set(c.owner_id for c in customers if c.owner_id)
    creator_ids = set(c.creator_id for c in customers if c.creator_id)
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
            'id': customer.id,
            'account_name': customer.account_name,
            'industry': customer.industry,
            'industry_info': industries_info.get(customer.industry),
            'city': customer.city,
            'address': customer.address,
            'company_scale': customer.company_scale,
            'source': customer.source,
            'status': customer.status,
            'owner_id': customer.owner_id,
            'source_lead_id': customer.source_lead_id,
            'default_procurement_method_id': customer.default_procurement_method_id,
            'return_reason': customer.return_reason,
            'returned_time': customer.returned_time,
            'creator_id': customer.creator_id,
            'created_time': customer.created_time,
            'last_modified_time': customer.last_modified_time,
            'version': customer.version,
            'score': customer.score,
            'score_updated_at': customer.score_updated_at,
            'owner_info': users_info.get(customer.owner_id) if customer.owner_id else None,
            'creator_info': users_info.get(customer.creator_id) if customer.creator_id else None,
            'default_procurement_method_info': procurement_methods_info.get(customer.default_procurement_method_id) if customer.default_procurement_method_id else None
        }
        result.append(CustomerListResponse(**customer_dict))
    
    return result


@router.get("/{customer_id}", response_model=CustomerDetailResponse, summary="获取客户详情", description="返回客户信息及其所有联系人列表")
def get_customer(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    contacts = contact_crud.get_by_customer_id(db, customer_id)
    
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
    
    return CustomerDetailResponse(
        **customer.__dict__,
        contacts=contacts,
        owner_info=owner_info,
        creator_info=creator_info,
        default_procurement_method_info=procurement_method_info,
        industry_info=industry_info
    )


@router.put("/{customer_id}", response_model=CustomerResponse, summary="编辑客户", description="更新客户信息")
def update_customer(
    customer_id: int,
    customer_update: CustomerUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    if customer_update.account_name:
        existing_customer = customer_crud.get_by_name(db, customer_update.account_name, team_id)
        if existing_customer and existing_customer.id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="客户名称已存在"
            )

    return customer_crud.update(db, customer, customer_update)


@router.patch("/{customer_id}/status", response_model=CustomerResponse, summary="更新客户状态", description="用于标记赢单、输单等关键状态变更")
async def update_customer_status(
    customer_id: int,
    status_update: CustomerStatusUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.feishu import feishu_service

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    new_status = int(status_update.status)
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

    return updated_customer


@router.patch("/{customer_id}/lose", response_model=CustomerResponse, summary="标记输单", description="将客户标记为输单，必须记录输单原因")
async def mark_customer_as_lost(
    customer_id: int,
    lose_data: CustomerLoseRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.feishu import feishu_service

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

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

    return updated_customer


@router.delete("/{customer_id}", response_model=MessageResponse, summary="删除客户", description="逻辑删除，需校验权限")
def delete_customer(
    customer_id: int,
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
def create_contact(
    customer_id: int,
    contact: ContactCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    existing_contact = contact_crud.get_by_mobile(db, contact.mobile, team_id)
    if existing_contact:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该手机号已存在联系人"
        )

    return contact_crud.create(db, contact, customer_id, team_id)


@router.get("/{customer_id}/contacts", response_model=List[ContactResponse], summary="查询联系人列表", description="获取指定客户下的全部联系人")
def get_contacts(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    return contact_crud.get_by_customer_id(db, customer_id, team_id)


@router.put("/contacts/{contact_id}", response_model=ContactResponse, summary="编辑联系人", description="更新联系人信息")
def update_contact(
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

    if contact_update.mobile:
        existing_contact = contact_crud.get_by_mobile(db, contact_update.mobile, team_id)
        if existing_contact and existing_contact.id != contact_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该手机号已存在联系人"
            )

    return contact_crud.update(db, contact, contact_update)


@router.patch("/contacts/{contact_id}/set-primary", response_model=ContactResponse, summary="设置主联系人", description="设置某联系人为主联系人")
def set_primary_contact(
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

    return contact_crud.set_primary(db, contact)


@router.delete("/contacts/{contact_id}", response_model=MessageResponse, summary="删除联系人", description="删除联系人")
def delete_contact(
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

    try:
        contact_crud.delete(db, contact)
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
    customer_id: int,
    return_data: CustomerReturnRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.role import role_crud

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

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
        customer_id=customer_id,
        previous_owner=previous_owner,
        returned_time=updated_customer.returned_time,
        return_reason=updated_customer.return_reason,
        message="客户已成功退回公海"
    )


@router.get("/public/list", response_model=List[CustomerResponse], summary="查询公海客户", description="获取公海池中的客户列表，支持动态排序")
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
    return customers


@router.post("/{customer_id}/claim", response_model=CustomerResponse, summary="领取客户", description="从公海池中领取客户")
def claim_customer(
    customer_id: int,
    claim_data: CustomerClaimRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    try:
        updated_customer = customer_crud.claim_customer(
            db, customer, claim_data.owner_id, team_id
        )
        return updated_customer
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{customer_id}/assign", response_model=CustomerResponse, summary="分配客户", description="系统管理员和销售总监可将客户分配给指定人员（无论客户是否有归属人）")
def assign_customer(
    customer_id: int,
    assign_data: CustomerAssignRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.role import role_crud

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    is_admin = "TEAM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes

    if not (is_admin or is_director):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有系统管理员和销售总监可以分配客户"
        )

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    try:
        updated_customer = customer_crud.assign_customer(
            db, customer, assign_data.owner_id, team_id
        )
        return updated_customer
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{customer_id}/regenerate-profile", response_model=MessageResponse, summary="重新生成客户档案", description="AI重新生成客户档案信息")
async def regenerate_profile(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.customer_profile_service import customer_profile_service

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    # 重置状态为 PENDING
    customer_crud.update_profile_status(db, customer_id, "PENDING")

    # 触发档案重新生成
    await customer_profile_service.trigger_generation(
        customer_id=customer_id,
        account_name=customer.account_name,
        source_lead_id=customer.source_lead_id,
        team_id=team_id
    )

    return MessageResponse(message="档案正在重新生成")
