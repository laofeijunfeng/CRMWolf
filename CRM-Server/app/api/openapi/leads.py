"""
线索开放接口路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.api.openapi.deps import require_api_permission, verify_api_key
from app.crud.lead import lead_crud
from app.crud.user import user_crud
from app.crud.customer import customer_crud
from app.models.lead import LeadStatus, LeadSource
from app.models.api_key import ApiKey
from app.schemas.openapi.common import OpenApiResponse, success_response, paginated_response
from app.schemas.openapi.lead import (
    OpenApiLeadCreate, OpenApiLeadConvert,
    OpenApiLeadResponse, OpenApiLeadStatusResponse,
    OpenApiLeadCreateResponse, OpenApiLeadConvertResponse,
    OpenApiLeadStatus, OpenApiLeadSource,
    LEAD_STATUS_NAMES, LEAD_SOURCE_NAMES
)
from app.services.data_masker import data_masker

router = APIRouter()


@router.post("/", summary="创建线索", description="外部系统录入新线索，同步至CRMWolf系统公海池或指定负责人")
async def create_lead(
    data: OpenApiLeadCreate = Body(..., description="线索数据"),
    api_key: ApiKey = Depends(require_api_permission("lead:create")),
    db: Session = Depends(get_db)
):
    """创建线索接口"""
    # 校验手机号格式
    if len(data.phone) < 11:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号格式不正确"
        )

    # 检查是否已存在
    existing_lead = lead_crud.get_by_contact_phone(db, data.phone)
    if existing_lead:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该手机号已存在线索"
        )

    # 映射来源枚举
    source_mapping = {
        OpenApiLeadSource.WEBSITE: LeadSource.WEBSITE_INQUIRY,
        OpenApiLeadSource.REFERRAL: LeadSource.REFERRAL,
        OpenApiLeadSource.EVENT: LeadSource.MARKETING_ACTIVITY,
        OpenApiLeadSource.COLD_CALL: LeadSource.COLD_CALL
    }

    # 创建线索数据
    from app.schemas.lead import LeadCreate
    lead_data = LeadCreate(
        lead_name=data.lead_name,
        source=source_mapping.get(data.source, LeadSource.OTHER),
        city="未知",  # 开放接口无城市字段，默认设置为未知
        contact_name=data.lead_name,
        contact_phone=data.phone,
        company_scale=None
    )

    # 创建线索（使用系统默认创建者）
    lead = lead_crud.create(db, lead_data, "openapi_system")

    # 如果指定了负责人，则分配
    if data.assign_user_id:
        user = user_crud.get_by_id(db, data.assign_user_id)
        if user:
            lead.owner_id = user.feishu_open_id
            db.commit()

    return success_response(
        OpenApiLeadCreateResponse(
            lead_id=lead.id,
            status="NEW"
        ),
        message="创建成功"
    )


@router.get("/", summary="查询线索列表", description="查询线索列表，支持筛选")
async def get_leads(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(None, description="线索状态筛选"),
    source: Optional[str] = Query(None, description="线索来源筛选"),
    api_key: ApiKey = Depends(require_api_permission("lead:list")),
    db: Session = Depends(get_db)
):
    """查询线索列表接口"""
    skip = (page - 1) * page_size

    # 构建查询条件 - get_multi 返回 (list, total)
    leads, total = lead_crud.get_multi(db, skip=skip, limit=page_size)

    # 转换为开放接口响应格式
    items = []
    for lead in leads:
        # 获取负责人信息
        owner_name = None
        if lead.owner_id:
            user = user_crud.get_by_feishu_open_id(db, lead.owner_id)
            if user:
                owner_name = user.name

        items.append(OpenApiLeadResponse(
            lead_id=lead.id,
            lead_name=lead.lead_name,
            phone=data_masker.mask_phone(lead.contact_phone),
            source=lead.source.name if lead.source else "OTHER",
            source_name=LEAD_SOURCE_NAMES.get(OpenApiLeadSource(lead.source.name), lead.source.value) if lead.source else "其他",
            company=None,  # 线索模型无公司字段
            industry=None,
            status=OpenApiLeadStatus(lead.status.name).value if lead.status else "NEW",
            status_name=LEAD_STATUS_NAMES.get(OpenApiLeadStatus(lead.status.name), "新线索") if lead.status else "新线索",
            owner_id=None,
            owner_name=owner_name,
            create_time=lead.created_time
        ))

    return paginated_response(items, total, page, page_size)


@router.get("/{lead_id}", summary="获取线索详情", description="获取线索详细信息")
async def get_lead(
    lead_id: int = Path(..., description="线索ID"),
    api_key: ApiKey = Depends(require_api_permission("lead:read")),
    db: Session = Depends(get_db)
):
    """获取线索详情接口"""
    lead = lead_crud.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    # 获取负责人信息
    owner_name = None
    if lead.owner_id:
        user = user_crud.get_by_feishu_open_id(db, lead.owner_id)
        if user:
            owner_name = user.name

    response = OpenApiLeadResponse(
        lead_id=lead.id,
        lead_name=lead.lead_name,
        phone=data_masker.mask_phone(lead.contact_phone),
        source=lead.source.name if lead.source else "OTHER",
        source_name=LEAD_SOURCE_NAMES.get(OpenApiLeadSource(lead.source.name), lead.source.value) if lead.source else "其他",
        company=None,
        industry=None,
        status=OpenApiLeadStatus(lead.status.name).value if lead.status else "NEW",
        status_name=LEAD_STATUS_NAMES.get(OpenApiLeadStatus(lead.status.name), "新线索") if lead.status else "新线索",
        owner_id=None,
        owner_name=owner_name,
        create_time=lead.created_time
    )

    return success_response(response)


@router.get("/{lead_id}/status", summary="查询线索状态", description="查询线索当前状态")
async def get_lead_status(
    lead_id: int = Path(..., description="线索ID"),
    api_key: ApiKey = Depends(require_api_permission("lead:read")),
    db: Session = Depends(get_db)
):
    """查询线索状态接口"""
    lead = lead_crud.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    response = OpenApiLeadStatusResponse(
        lead_id=lead.id,
        status=OpenApiLeadStatus(lead.status.name).value if lead.status else "NEW",
        status_name=LEAD_STATUS_NAMES.get(OpenApiLeadStatus(lead.status.name), "新线索") if lead.status else "新线索"
    )

    return success_response(response)


@router.post("/{lead_id}/convert", summary="线索转化", description="线索转化为客户")
async def convert_lead(
    lead_id: int = Path(..., description="线索ID"),
    data: OpenApiLeadConvert = Body(..., description="转化数据"),
    api_key: ApiKey = Depends(require_api_permission("lead:convert")),
    db: Session = Depends(get_db)
):
    """线索转化为客户接口"""
    lead = lead_crud.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    if lead.status == LeadStatus.CONVERTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="线索已转化"
        )

    # 执行转化
    from app.schemas.customer import ConvertLeadToCustomer
    convert_data = ConvertLeadToCustomer(
        lead_id=lead_id,
        account_name=data.account_name,
        industry=data.industry,
        address=None,
        default_procurement_method_id=data.default_procurement_method_id
    )

    customer, contact = customer_crud.convert_from_lead(
        db=db,
        lead_id=lead_id,
        account_name=data.account_name,
        industry=data.industry,
        address=None,
        default_procurement_method_id=data.default_procurement_method_id,
        creator_id="openapi_system",
        operator_name="开放接口"
    )

    response = OpenApiLeadConvertResponse(
        customer_id=customer.id,
        contact_id=contact.id,
        lead_id=lead_id
    )

    return success_response(response, message="转化成功")