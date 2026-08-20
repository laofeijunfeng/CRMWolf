from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import json
from app.core.database import get_db
from app.core.deps import get_current_active_user, check_lead_access, check_lead_owner, require_permission, get_current_user_team, check_lead_delete_permission
from app.crud.customer import customer_crud
from app.crud.lead import lead_crud, lead_follow_up_crud
from app.crud.user import user_crud
from app.schemas.lead import (
    LeadCreate, LeadUpdate, LeadResponse, LeadListResponse, LeadDetailResponse,
    LeadFollowUpCreate, LeadFollowUpResponse,
    LeadAssignRequest, LeadConvertRequest,
    LeadBatchImportRequest, LeadBatchImportResponse,
    LeadTrendResponse, LeadConversionResponse, LeadMarkInvalidRequest
)
from app.schemas.common import PaginatedResponse
from app.models.lead import LeadStatus
from app.models.user import User
from app.services.acquisition_source_service import (
    AcquisitionSourceError,
    build_source_info,
    get_by_id,
    map_sources_by_ids,
    resolve_public_ids_to_ids,
)
from app.utils.time import business_now
from app.core.list_query import (
    enforce_owner_view_scope,
    optional_request_list_query,
    run_or_400,
    uses_unified_list_query,
)

router = APIRouter(prefix="/v1/leads", tags=["线索管理"])


def _build_lead_follow_up_response(follow_up, lead_public_id: str, creator_info=None) -> LeadFollowUpResponse:
    return LeadFollowUpResponse(
        id=follow_up.id,
        lead_id=lead_public_id,
        content=follow_up.content,
        method=follow_up.method,
        next_follow_time=follow_up.next_follow_time,
        next_action=follow_up.next_action,
        creator_id=follow_up.creator_id,
        created_time=follow_up.created_time,
        creator_info=creator_info,
    )


def _lead_name_conflict_error(db: Session, lead_name: str, team_id: int) -> Optional[str]:
    if lead_crud.get_by_name(db, lead_name, team_id):
        return "线索名称已存在"
    if customer_crud.get_by_name(db, lead_name, team_id):
        return "该名称已存在客户，请直接在客户下跟进"
    return None


def _ensure_lead_name_available(db: Session, lead_name: str, team_id: int) -> None:
    error = _lead_name_conflict_error(db, lead_name, team_id)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )


def parse_filter_conditions(filters: Optional[str]):
    if not filters:
        return None

    try:
        parsed_filters = json.loads(filters)
        if isinstance(parsed_filters, dict):
            parsed_filters = parsed_filters.get("filters", [])
        if not isinstance(parsed_filters, list):
            raise ValueError("filters must be a list")
        return parsed_filters
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="筛选条件格式不正确"
        )


def _raise_source_error(exc: AcquisitionSourceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _lead_source_fields(db: Session, lead, source_map: Optional[dict] = None) -> dict:
    source_row = None
    if lead.source_id:
        if source_map is not None:
            source_row = source_map.get(int(lead.source_id))
        else:
            source_row = get_by_id(db, lead.source_id, lead.team_id)
    current_name = source_row.name if source_row else (lead.source or "")
    return {
        "source": current_name,
        "source_info": build_source_info(source_row),
    }


def _build_lead_response(db: Session, lead) -> LeadResponse:
    payload = {
        "id": lead.public_id,
        "public_id": lead.public_id,
        "lead_name": lead.lead_name,
        "city": lead.city,
        "contact_name": lead.contact_name,
        "contact_phone": lead.contact_phone,
        "company_scale": lead.company_scale,
        "owner_id": lead.owner_id,
        "status": lead.status,
        "invalid_reason": lead.invalid_reason,
        "pool_id": lead.pool_id,
        "creator_id": lead.creator_id,
        "created_time": lead.created_time,
        "last_modified_time": lead.last_modified_time,
        "version": lead.version,
        **_lead_source_fields(db, lead),
    }
    return LeadResponse(**payload)


def _build_user_info_map(db: Session, user_ids: set[str]) -> dict[str, dict]:
    numeric_user_ids = [int(user_id) for user_id in user_ids if user_id and user_id.isdigit()]
    if not numeric_user_ids:
        return {}

    users = db.query(User).filter(User.id.in_(numeric_user_ids)).all()
    return {
        str(user.id): {
            "id": str(user.id),
            "name": user.name,
            "avatar_url": user.avatar_url,
        }
        for user in users
    }


def _build_lead_list_responses(db: Session, leads: List) -> List[LeadListResponse]:
    owner_ids = {lead.owner_id for lead in leads if lead.owner_id}
    users_info = _build_user_info_map(db, owner_ids)
    source_map = map_sources_by_ids(
        db,
        leads[0].team_id,
        [lead.source_id for lead in leads],
    ) if leads else {}

    result = []
    for lead in leads:
        lead_dict = {
            "id": lead.public_id,
            "public_id": lead.public_id,
            "lead_name": lead.lead_name,
            **_lead_source_fields(db, lead, source_map),
            "city": lead.city,
            "contact_name": lead.contact_name,
            "contact_phone": lead.contact_phone,
            "company_scale": lead.company_scale,
            "owner_id": lead.owner_id,
            "status": lead.status,
            "invalid_reason": lead.invalid_reason,
            "pool_id": lead.pool_id,
            "creator_id": lead.creator_id,
            "created_time": lead.created_time,
            "last_modified_time": lead.last_modified_time,
            "version": lead.version,
            "owner_info": users_info.get(lead.owner_id) if lead.owner_id else None,
        }
        result.append(LeadListResponse(**lead_dict))

    return result


@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED, summary="创建线索", description="创建新的线索")
def create_lead(
    lead: LeadCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    _ensure_lead_name_available(db, lead.lead_name, team_id)

    try:
        created = lead_crud.create(db, lead, str(current_user.id), team_id)
    except AcquisitionSourceError as exc:
        _raise_source_error(exc)
    return _build_lead_response(db, created)


@router.post("/batch-import", response_model=LeadBatchImportResponse, summary="批量导入线索", description="批量导入线索（最多100条）")
def batch_import_leads(
    request: LeadBatchImportRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    success_count = 0
    failed_count = 0
    failed_items = []

    for lead_data in request.leads:
        try:
            conflict_error = _lead_name_conflict_error(db, lead_data.lead_name, team_id)
            if conflict_error:
                failed_count += 1
                failed_items.append({
                    "lead_name": lead_data.lead_name,
                    "contact_phone": lead_data.contact_phone,
                    "error": conflict_error,
                })
                continue

            lead_crud.create(db, lead_data, str(current_user.id), team_id, import_by_name=True)
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


@router.get("/", response_model=PaginatedResponse[LeadListResponse], summary="查询线索列表", description="查询线索列表，支持多条件筛选和动态排序，返回负责人信息")
def get_leads(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    status: Optional[LeadStatus] = Query(None, description="线索状态"),
    source_public_id: Optional[str] = Query(None, description="获客来源对外ID，多个值用逗号分隔"),
    city: Optional[str] = Query(None, description="所在城市"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    filters: Optional[str] = Query(None, description="通用筛选条件 JSON"),
    sorts: Optional[str] = Query(None, description="通用排序条件 JSON"),
    owner_id: Optional[str] = Query(None, description="按负责人ID筛选（支持 me/my 表示当前用户）"),
    order_by: Optional[str] = Query(None, description="排序字段"),
    order_dir: Optional[str] = Query(None, description="排序方向（asc/desc）"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.permission import permission_crud

    # 获取用户权限码
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有 view:all 权限
    has_view_all = "lead:view:all" in permission_codes

    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    if uses_unified_list_query(filters=parsed_filters, sorts=parsed_sorts):
        owner_id = enforce_owner_view_scope(
            parsed_filters or [],
            current_user_id=str(current_user.id),
            has_view_all=has_view_all,
            permission_detail="只能查看自己负责的线索，或需要 lead:view:all 权限查看他人数据",
        )
    else:
        if owner_id is not None and owner_id not in ["me", "my"] and owner_id != str(current_user.id):
            if not has_view_all:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="只能查看自己负责的线索，或需要 lead:view:all 权限查看他人数据"
                )
        if owner_id in ["me", "my"]:
            owner_id = str(current_user.id)
        if owner_id is None and not has_view_all:
            owner_id = str(current_user.id)

    source_ids = None
    if source_public_id is not None:
        source_ids = resolve_public_ids_to_ids(db, team_id, _split_csv(source_public_id))

    leads, total = run_or_400(lambda: lead_crud.get_multi(
        db, team_id=team_id, skip=skip, limit=limit,
        status=status, source_ids=source_ids, city=city,
        owner_id=owner_id, keyword=keyword,
        filters=parsed_filters, sorts=parsed_sorts,
        order_by=order_by, order_dir=order_dir
    ))

    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[LeadListResponse](
        items=_build_lead_list_responses(db, leads),
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


@router.get("/statistics", summary="线索统计", description="获取线索统计数据")
def get_lead_statistics(
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.permission import permission_crud

    # 获取用户权限码
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有 view:all 权限
    has_view_all = "lead:view:all" in permission_codes

    owner_id = None
    if not has_view_all:
        owner_id = str(current_user.id)

    return lead_crud.get_statistics(db, team_id, owner_id)


@router.get("/{lead_id}", response_model=LeadDetailResponse, summary="获取线索详情", description="获取线索详情及跟进记录，返回负责人和创建人信息")
def get_lead(
    lead_id: str,
    lead = Depends(check_lead_access),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text

    follow_ups = lead_follow_up_crud.get_by_lead_id(db, lead.id)

    owner_info = None
    if lead.owner_id:
        owner_data = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :owner_id
        """), {"owner_id": int(lead.owner_id)}).first()

        if owner_data:
            owner_info = {
                "id": str(owner_data[0]),
                "name": owner_data[1],
                "avatar_url": owner_data[2]
            }

    creator_info = None
    if lead.creator_id:
        creator_data = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :creator_id
        """), {"creator_id": int(lead.creator_id)}).first()

        if creator_data:
            creator_info = {
                "id": str(creator_data[0]),
                "name": creator_data[1],
                "avatar_url": creator_data[2]
            }

    enriched_follow_ups = []
    for follow_up in follow_ups:
        follow_up_dict = {
            "id": follow_up.id,
            "lead_id": lead.public_id,
            "content": follow_up.content,
            "method": follow_up.method,
            "next_follow_time": follow_up.next_follow_time,
            "next_action": follow_up.next_action,
            "creator_id": follow_up.creator_id,
            "created_time": follow_up.created_time,
            "creator_info": None
        }

        if follow_up.creator_id:
            creator_data = db.execute(text("""
                SELECT id, name, avatar_url
                FROM users
                WHERE id = :creator_id
            """), {"creator_id": int(follow_up.creator_id)}).first()

            if creator_data:
                follow_up_dict["creator_info"] = {
                    "id": str(creator_data[0]),
                    "name": creator_data[1],
                    "avatar_url": creator_data[2]
                }

        enriched_follow_ups.append(LeadFollowUpResponse(**follow_up_dict))

    lead_payload = {
        **lead.__dict__,
        "id": lead.public_id,
        "public_id": lead.public_id,
        **_lead_source_fields(db, lead),
    }
    return LeadDetailResponse(
        **lead_payload,
        follow_ups=enriched_follow_ups,
        owner_info=owner_info,
        creator_info=creator_info
    )


@router.put("/{lead_id}", response_model=LeadResponse, summary="编辑线索", description="更新线索信息")
def update_lead(
    lead_id: str,
    lead_update: LeadUpdate,
    lead = Depends(check_lead_owner),
    db: Session = Depends(get_db)
):
    try:
        updated = lead_crud.update(db, lead, lead_update)
    except AcquisitionSourceError as exc:
        _raise_source_error(exc)
    return _build_lead_response(db, updated)


@router.delete("/{lead_id}", response_model=LeadResponse, summary="删除线索", description="删除线索")
def delete_lead(
    lead_id: str,
    lead = Depends(check_lead_delete_permission),
    db: Session = Depends(get_db)
):
    try:
        return lead_crud.delete(db, lead.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{lead_id}/claim", response_model=LeadResponse, summary="领取线索", description="从公海领取线索")
async def claim_lead(
    lead_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.feishu import feishu_service

    lead = lead_crud.get_by_public_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在或不属于当前团队"
        )

    if lead.owner_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该线索已被领取"
        )

    claimed_lead = lead_crud.claim(db, lead.id, str(current_user.id), team_id)

    await feishu_service.notify_lead_claimed(
        str(current_user.id),
        lead.lead_name
    )

    return claimed_lead


@router.post("/{lead_id}/assign", response_model=LeadResponse, summary="分配线索", description="将线索分配给指定负责人")
async def assign_lead(
    lead_id: str,
    request: LeadAssignRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.role import role_crud
    from app.services.feishu import feishu_service

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    is_admin = "TEAM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes

    if not (is_admin or is_director):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员或销售总监可以分配线索"
        )

    target_user = user_crud.get_by_id(db, int(request.owner_id))
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目标用户不存在"
        )

    lead = lead_crud.get_by_public_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在或不属于当前团队"
        )

    assigned_lead = lead_crud.assign(db, lead.id, request.owner_id)

    await feishu_service.notify_lead_assigned(
        request.owner_id,
        lead.lead_name,
        lead.contact_name,
        lead.contact_phone
    )

    return assigned_lead


@router.post("/{lead_id}/return", response_model=LeadResponse, summary="退回线索", description="将线索退回公海")
def return_lead(
    lead_id: str,
    team_id: int = Depends(get_current_user_team),
    lead = Depends(check_lead_owner),
    db: Session = Depends(get_db)
):
    if lead.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该线索已在公海中"
        )

    return lead_crud.return_to_pool(db, lead.id, team_id)


@router.post("/{lead_id}/follow-ups", response_model=LeadFollowUpResponse, status_code=status.HTTP_201_CREATED, summary="添加跟进记录", description="为线索添加跟进记录")
def add_follow_up(
    lead_id: str,
    follow_up: LeadFollowUpCreate,
    team_id: int = Depends(get_current_user_team),
    lead = Depends(check_lead_owner),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    created = lead_follow_up_crud.create(db, follow_up, lead.id, str(current_user.id), team_id)
    return _build_lead_follow_up_response(created, lead.public_id)


@router.get("/{lead_id}/follow-ups", response_model=List[LeadFollowUpResponse], summary="获取跟进记录", description="获取线索的跟进记录列表")
def get_follow_ups(
    lead_id: str,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    lead = Depends(check_lead_access),
    db: Session = Depends(get_db)
):
    follow_ups = lead_follow_up_crud.get_by_lead_id(db, lead.id, skip, limit)
    return [_build_lead_follow_up_response(follow_up, lead.public_id) for follow_up in follow_ups]


@router.delete("/{lead_id}/follow-ups/{follow_up_id}", summary="删除跟进记录", description="删除线索的跟进记录")
def delete_follow_up(
    lead_id: str,
    follow_up_id: int,
    lead = Depends(check_lead_access),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    follow_up = lead_follow_up_crud.get_by_id(db, follow_up_id)
    if not follow_up:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="跟进记录不存在"
        )

    if follow_up.lead_id != lead.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="跟进记录不属于该线索"
        )

    if follow_up.creator_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除此记录"
        )

    lead_follow_up_crud.delete(db, follow_up_id)
    return {"message": "删除成功"}


@router.post("/{lead_id}/convert", response_model=LeadResponse, summary="线索转化", description="将线索转化为客户")
def convert_lead(
    lead_id: str,
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

    converted_lead = lead_crud.convert(db, lead.id)

    return converted_lead


@router.post("/{lead_id}/mark-invalid", response_model=LeadResponse, summary="标记无效", description="将线索标记为无效，必须记录无效原因")
def mark_lead_invalid(
    lead_id: str,
    request_data: LeadMarkInvalidRequest,
    team_id: int = Depends(get_current_user_team),
    lead = Depends(check_lead_owner),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if lead.status == LeadStatus.INVALID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该线索已标记为无效"
        )

    return lead_crud.mark_invalid(db, lead.id, request_data.reason, str(current_user.id), current_user.name, team_id)


@router.get("/public/list", response_model=PaginatedResponse[LeadResponse], summary="公海线索", description="获取公海中的线索列表（团队公海池）")
def get_public_leads(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    filters: Optional[str] = Query(None, description="通用筛选条件 JSON"),
    sorts: Optional[str] = Query(None, description="通用排序条件 JSON"),
    order_by: Optional[str] = Query(None, description="排序字段"),
    order_dir: Optional[str] = Query(None, description="排序方向（asc/desc）"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    leads, total = run_or_400(lambda: lead_crud.get_public_leads(
        db,
        team_id,
        skip,
        limit,
        filters=parsed_filters,
        sorts=parsed_sorts,
        order_by=order_by,
        order_dir=order_dir
    ))
    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[LeadResponse](
        items=leads,
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


analytics_router = APIRouter(prefix="/v1/analytics/leads", tags=["线索分析"])


@analytics_router.get("/trend", response_model=List[LeadTrendResponse], summary="新增线索趋势", description="按时间统计新增线索数量")
def get_lead_trend(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func, extract
    from app.models.lead import Lead

    start_date = business_now() - timedelta(days=days)

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
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    results = lead_crud.get_conversion_stats(db, team_id)

    source_map = map_sources_by_ids(db, team_id, [result.source_id for result in results])
    payload = []
    for result in results:
        source_row = source_map.get(int(result.source_id)) if result.source_id is not None else None
        current_name = source_row.name if source_row else "未知"
        payload.append(
            LeadConversionResponse(
                source=current_name,
                source_public_id=source_row.public_id if source_row else None,
                source_name=current_name,
                total=result.total,
                converted=result.converted or 0,
                conversion_rate=round((result.converted or 0) / result.total * 100, 2) if result.total > 0 else 0
            )
        )
    return payload
