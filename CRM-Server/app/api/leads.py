from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.deps import get_current_active_user, check_lead_access, check_lead_owner, require_permission
from app.crud.lead import lead_crud, lead_follow_up_crud
from app.crud.user import user_crud
from app.schemas.lead import (
    LeadCreate, LeadUpdate, LeadResponse, LeadListResponse, LeadDetailResponse,
    LeadFollowUpCreate, LeadFollowUpResponse,
    LeadAssignRequest, LeadConvertRequest,
    LeadBatchImportRequest, LeadBatchImportResponse,
    LeadTrendResponse, LeadConversionResponse
)
from app.models.lead import LeadStatus, LeadSource

router = APIRouter(prefix="/api/v1/leads", tags=["线索管理"])


@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED, summary="创建线索", description="创建新的线索")
def create_lead(
    lead: LeadCreate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    existing_lead = lead_crud.get_by_contact_phone(db, lead.contact_phone)
    if existing_lead:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该手机号已存在线索"
        )
    
    return lead_crud.create(db, lead, current_user.feishu_open_id)


@router.post("/batch-import", response_model=LeadBatchImportResponse, summary="批量导入线索", description="批量导入线索（最多100条）")
def batch_import_leads(
    request: LeadBatchImportRequest,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    success_count = 0
    failed_count = 0
    failed_items = []
    
    for lead_data in request.leads:
        try:
            existing_lead = lead_crud.get_by_contact_phone(db, lead_data.contact_phone)
            if existing_lead:
                failed_count += 1
                failed_items.append({
                    "lead_name": lead_data.lead_name,
                    "contact_phone": lead_data.contact_phone,
                    "error": "该手机号已存在线索"
                })
                continue
            
            lead_crud.create(db, lead_data, current_user.feishu_open_id)
            success_count += 1
        except Exception as e:
            failed_count += 1
            failed_items.append({
                "lead_name": lead_data.lead_name,
                "contact_phone": lead_data.contact_phone,
                "error": str(e)
            })
    
    return LeadBatchImportResponse(
        total=len(request.leads),
        success=success_count,
        failed=failed_count,
        failed_items=failed_items
    )


@router.get("/", response_model=List[LeadListResponse], summary="查询线索列表", description="查询线索列表，支持多条件筛选，返回负责人信息")
def get_leads(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    status: Optional[LeadStatus] = Query(None, description="线索状态"),
    source: Optional[LeadSource] = Query(None, description="线索来源"),
    city: Optional[str] = Query(None, description="所在城市"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    from app.crud.role import role_crud
    
    user_roles = role_crud.get_user_roles(db, current_user.id)
    role_codes = {r.code for r in user_roles}
    
    is_admin = "SYSTEM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    
    owner_id = None
    if not (is_admin or is_director):
        owner_id = current_user.feishu_open_id
    
    leads, total = lead_crud.get_multi(
        db, skip=skip, limit=limit,
        status=status, source=source, city=city,
        owner_id=owner_id, keyword=keyword
    )
    
    result = []
    for lead in leads:
        lead_dict = {
            "id": lead.id,
            "lead_name": lead.lead_name,
            "source": lead.source,
            "city": lead.city,
            "contact_name": lead.contact_name,
            "contact_phone": lead.contact_phone,
            "company_scale": lead.company_scale,
            "owner_id": lead.owner_id,
            "status": lead.status,
            "pool_id": lead.pool_id,
            "creator_id": lead.creator_id,
            "created_time": lead.created_time,
            "last_modified_time": lead.last_modified_time,
            "version": lead.version,
            "owner_info": None
        }
        
        if lead.owner_id:
            owner_info = db.execute(text("""
                SELECT feishu_open_id, name, avatar_url
                FROM users
                WHERE feishu_open_id = :owner_id
            """), {"owner_id": lead.owner_id}).first()
            
            if owner_info:
                lead_dict["owner_info"] = {
                    "id": owner_info[0],
                    "name": owner_info[1],
                    "avatar_url": owner_info[2]
                }
        
        result.append(LeadListResponse(**lead_dict))
    
    return result


@router.get("/statistics", summary="线索统计", description="获取线索统计数据")
def get_lead_statistics(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.role import role_crud
    
    user_roles = role_crud.get_user_roles(db, current_user.id)
    role_codes = {r.code for r in user_roles}
    
    is_admin = "SYSTEM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    
    owner_id = None
    if not (is_admin or is_director):
        owner_id = current_user.feishu_open_id
    
    return lead_crud.get_statistics(db, owner_id)


@router.get("/{lead_id}", response_model=LeadDetailResponse, summary="获取线索详情", description="获取线索详情及跟进记录，返回负责人和创建人信息")
def get_lead(
    lead_id: int,
    lead = Depends(check_lead_access),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    
    follow_ups = lead_follow_up_crud.get_by_lead_id(db, lead_id)
    
    owner_info = None
    if lead.owner_id:
        owner_data = db.execute(text("""
            SELECT feishu_open_id, name, avatar_url
            FROM users
            WHERE feishu_open_id = :owner_id
        """), {"owner_id": lead.owner_id}).first()
        
        if owner_data:
            owner_info = {
                "id": owner_data[0],
                "name": owner_data[1],
                "avatar_url": owner_data[2]
            }
    
    creator_info = None
    if lead.creator_id:
        creator_data = db.execute(text("""
            SELECT feishu_open_id, name, avatar_url
            FROM users
            WHERE feishu_open_id = :creator_id
        """), {"creator_id": lead.creator_id}).first()
        
        if creator_data:
            creator_info = {
                "id": creator_data[0],
                "name": creator_data[1],
                "avatar_url": creator_data[2]
            }
    
    enriched_follow_ups = []
    for follow_up in follow_ups:
        follow_up_dict = {
            "id": follow_up.id,
            "lead_id": follow_up.lead_id,
            "content": follow_up.content,
            "method": follow_up.method,
            "next_follow_time": follow_up.next_follow_time,
            "creator_id": follow_up.creator_id,
            "created_time": follow_up.created_time,
            "creator_info": None
        }
        
        if follow_up.creator_id:
            creator_data = db.execute(text("""
                SELECT feishu_open_id, name, avatar_url
                FROM users
                WHERE feishu_open_id = :creator_id
            """), {"creator_id": follow_up.creator_id}).first()
            
            if creator_data:
                follow_up_dict["creator_info"] = {
                    "id": creator_data[0],
                    "name": creator_data[1],
                    "avatar_url": creator_data[2]
                }
        
        enriched_follow_ups.append(LeadFollowUpResponse(**follow_up_dict))
    
    return LeadDetailResponse(
        **lead.__dict__,
        follow_ups=enriched_follow_ups,
        owner_info=owner_info,
        creator_info=creator_info
    )


@router.put("/{lead_id}", response_model=LeadResponse, summary="编辑线索", description="更新线索信息")
def update_lead(
    lead_id: int,
    lead_update: LeadUpdate,
    lead = Depends(check_lead_owner),
    db: Session = Depends(get_db)
):
    return lead_crud.update(db, lead, lead_update)


@router.delete("/{lead_id}", response_model=LeadResponse, summary="删除线索", description="删除线索")
def delete_lead(
    lead_id: int,
    lead = Depends(check_lead_owner),
    db: Session = Depends(get_db)
):
    return lead_crud.delete(db, lead_id)


@router.post("/{lead_id}/claim", response_model=LeadResponse, summary="领取线索", description="从公海领取线索")
async def claim_lead(
    lead_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.feishu import feishu_service
    
    lead = lead_crud.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )
    
    if lead.owner_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该线索已被领取"
        )
    
    claimed_lead = lead_crud.claim(db, lead_id, current_user.feishu_open_id)
    
    await feishu_service.notify_lead_claimed(
        current_user.feishu_open_id,
        lead.lead_name
    )
    
    return claimed_lead


@router.post("/{lead_id}/assign", response_model=LeadResponse, summary="分配线索", description="将线索分配给指定负责人")
async def assign_lead(
    lead_id: int,
    request: LeadAssignRequest,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.role import role_crud
    from app.services.feishu import feishu_service
    
    user_roles = role_crud.get_user_roles(db, current_user.id)
    role_codes = {r.code for r in user_roles}
    
    is_admin = "SYSTEM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    
    if not (is_admin or is_director):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员或销售总监可以分配线索"
        )
    
    target_user = user_crud.get_by_feishu_open_id(db, request.owner_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目标用户不存在"
        )
    
    lead = lead_crud.get_by_id(db, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )
    
    assigned_lead = lead_crud.assign(db, lead_id, request.owner_id)
    
    await feishu_service.notify_lead_assigned(
        request.owner_id,
        lead.lead_name,
        lead.contact_name,
        lead.contact_phone
    )
    
    return assigned_lead


@router.post("/{lead_id}/return", response_model=LeadResponse, summary="退回线索", description="将线索退回公海")
def return_lead(
    lead_id: int,
    lead = Depends(check_lead_owner),
    db: Session = Depends(get_db)
):
    if lead.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该线索已在公海中"
        )
    
    return lead_crud.return_to_pool(db, lead_id)


@router.post("/{lead_id}/follow-ups", response_model=LeadFollowUpResponse, status_code=status.HTTP_201_CREATED, summary="添加跟进记录", description="为线索添加跟进记录")
def add_follow_up(
    lead_id: int,
    follow_up: LeadFollowUpCreate,
    lead = Depends(check_lead_owner),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return lead_follow_up_crud.create(db, follow_up, lead_id, current_user.feishu_open_id)


@router.get("/{lead_id}/follow-ups", response_model=List[LeadFollowUpResponse], summary="获取跟进记录", description="获取线索的跟进记录列表")
def get_follow_ups(
    lead_id: int,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    lead = Depends(check_lead_access),
    db: Session = Depends(get_db)
):
    return lead_follow_up_crud.get_by_lead_id(db, lead_id, skip, limit)


@router.post("/{lead_id}/convert", response_model=LeadResponse, summary="线索转化", description="将线索转化为客户")
def convert_lead(
    lead_id: int,
    request: LeadConvertRequest,
    lead = Depends(check_lead_owner),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if lead.status == LeadStatus.CONVERTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该线索已转化"
        )
    
    converted_lead = lead_crud.convert(db, lead_id)
    
    return converted_lead


@router.post("/{lead_id}/mark-invalid", response_model=LeadResponse, summary="标记无效", description="将线索标记为无效")
def mark_lead_invalid(
    lead_id: int,
    lead = Depends(check_lead_owner),
    db: Session = Depends(get_db)
):
    if lead.status == LeadStatus.INVALID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该线索已标记为无效"
        )
    
    return lead_crud.mark_invalid(db, lead_id)


@router.get("/public/list", response_model=List[LeadResponse], summary="公海线索", description="获取公海中的线索列表")
def get_public_leads(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return lead_crud.get_public_leads(db, skip, limit)


@router.get("/my/list", response_model=List[LeadResponse], summary="我的线索", description="获取当前用户负责的线索列表")
def get_my_leads(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return lead_crud.get_leads_by_owner(db, current_user.feishu_open_id, skip, limit)


@router.get("/follow-up/reminder", response_model=List[LeadResponse], summary="待跟进线索", description="获取需要跟进的线索列表")
def get_leads_need_follow_up(
    days: int = Query(7, ge=1, le=30, description="天数"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return lead_crud.get_leads_need_follow_up(db, current_user.feishu_open_id, days)


analytics_router = APIRouter(prefix="/api/v1/analytics/leads", tags=["线索分析"])


@analytics_router.get("/trend", response_model=List[LeadTrendResponse], summary="新增线索趋势", description="按时间统计新增线索数量")
def get_lead_trend(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func, extract
    from app.models.lead import Lead
    
    start_date = datetime.now() - timedelta(days=days)
    
    results = db.query(
        func.date(Lead.created_time).label('date'),
        func.count(Lead.id).label('count')
    ).filter(
        Lead.created_time >= start_date
    ).group_by(
        func.date(Lead.created_time)
    ).order_by(
        func.date(Lead.created_time)
    ).all()
    
    return [
        LeadTrendResponse(
            date=str(result.date),
            count=result.count
        )
        for result in results
    ]


@analytics_router.get("/conversion", response_model=List[LeadConversionResponse], summary="线索转化分析", description="统计各来源线索的转化率")
def get_lead_conversion(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func
    from app.models.lead import Lead
    
    results = db.query(
        Lead.source.label('source'),
        func.count(Lead.id).label('total'),
        func.sum(func.case((Lead.status == LeadStatus.CONVERTED, 1), else_=0)).label('converted')
    ).group_by(
        Lead.source
    ).all()
    
    return [
        LeadConversionResponse(
            source=result.source.value if result.source else "未知",
            total=result.total,
            converted=result.converted or 0,
            conversion_rate=round((result.converted or 0) / result.total * 100, 2) if result.total > 0 else 0
        )
        for result in results
    ]
