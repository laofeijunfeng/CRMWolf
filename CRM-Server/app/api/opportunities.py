from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.core.database import get_db
from app.core.list_query import (
    enforce_owner_view_scope,
    optional_request_list_query,
    run_or_400,
    uses_unified_list_query,
)
from app.core.deps import (
    check_customer_edit_permission,
    check_customer_view_permission,
    check_opportunity_delete_permission,
    check_opportunity_edit_permission,
    check_opportunity_view_permission,
    get_current_active_user,
    get_current_user_team,
    require_permission,
)
from app.crud.customer import customer_crud
from app.crud.deal_journey import deal_journey_crud
from app.crud.opportunity import opportunity_crud
from app.models.approval import ApprovalStatus
from app.core.list_export import (
    OPPORTUNITIES_LIST_EXPORT_CATALOG,
    create_list_export_file,
    iter_batches,
    list_export_file_response,
    run_list_export_or_400,
)
from app.core.database import SessionLocal
from app.schemas.list_export import OpportunityListExportRequest
from fastapi.responses import FileResponse
from typing import Iterator
from app.schemas.common import PaginatedResponse
from app.schemas.opportunity import (
    MessageResponse,
    OpportunityCreate,
    OpportunityDealJourneyUpdate,
    OpportunityDetailResponse,
    OpportunityListResponse,
    OpportunityLose,
    OpportunityMoveToStage,
    OpportunityProcurementStageInfo,
    OpportunityResponse,
    OpportunityUpdate,
    OpportunityWin,
    SalesFunnelResponse,
    StageDurationResponse,
)
from app.services.approval_transaction_manager import approval_transaction_manager
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeRefreshInput,
    customer_business_object_intelligence_service,
)
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.services.outbound_notification_job_service import outbound_notification_job_service
from app.services.opportunity_presenter import (
    customer_info_dict as _customer_info_dict,
    customer_public_id as _customer_public_id,
    deal_journey_public_id as _deal_journey_public_id,
    deal_journey_public_id_map as _deal_journey_public_id_map,
    opportunity_detail_response,
    opportunity_product_payload as _opportunity_product_payload,
    opportunity_product_payloads as _opportunity_product_payloads,
    opportunity_response_dict as _opportunity_response_dict,
    resolve_opportunity_approval_phase as _resolve_opportunity_approval_phase,
)
from app.utils.public_id import is_deal_journey_public_id

router = APIRouter(prefix="/v1/opportunities", tags=["商机管理"])


OPPORTUNITY_STATUS_LABELS = {0: "跟进中", 1: "已赢单", 2: "已输单"}
LICENSE_TYPE_LABELS = {"SUBSCRIPTION": "订阅", "PERPETUAL": "买断"}
PURCHASE_TYPE_LABELS = {"NEW": "新购", "RENEWAL": "续购", "EXPANSION": "增购"}
APPROVAL_PHASE_LABELS = {
    "draft": "待提交",
    "pending_review": "审批中",
    "pending": "审批中",
    "approved": "已通过",
    "rejected": "已拒绝",
}



def _ensure_opportunity_not_pending(db: Session, opportunity, team_id: Optional[int]) -> None:
    if _resolve_opportunity_approval_phase(db, opportunity, team_id) == ApprovalPhase.PENDING_REVIEW.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="商机审批中，暂不能进行该操作"
        )


def _ensure_opportunity_approved(db: Session, opportunity, team_id: Optional[int]) -> None:
    if _resolve_opportunity_approval_phase(db, opportunity, team_id) != ApprovalPhase.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="商机审批通过后才能进行该操作"
        )




def _build_opportunity_intelligence_change(
    opportunity,
    *,
    change_type: Literal["created", "updated", "deleted"],
    actor_id: str | None,
) -> CustomerBusinessObjectChangeRefreshInput:
    change = customer_business_object_intelligence_service.build_change(
        None,
        source_type="opportunity",
        business_object=opportunity,
        change_type=change_type,
        actor_id=actor_id,
    )
    if change is None:
        raise ValueError("商机缺少客户智能刷新所需字段")
    return change


async def _trigger_opportunity_intelligence_refresh(
    db: Session,
    change: CustomerBusinessObjectChangeRefreshInput,
) -> None:
    customer_business_object_intelligence_service.enqueue_change_refresh_after_commit(change)




@router.post("/", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED, summary="创建商机", description="为指定客户创建商机")
async def create_opportunity(
    opportunity: OpportunityCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("opportunity:create")),
    db: Session = Depends(get_db)
):
    customer = check_customer_edit_permission(opportunity.customer_id, team_id, current_user, db)
    opportunity.customer_id = customer.id

    from app.crud.user import user_crud

    submitter_id = str(current_user.id)
    submitter = user_crud.get_by_id(db, int(current_user.id))
    submitter_name = submitter.name if submitter else None

    entity, approval, error_msg = approval_transaction_manager.create_with_approval(
        db=db,
        business_type=BusinessType.OPPORTUNITY,
        entity_create_func=lambda: opportunity_crud.create_without_commit(
            db,
            opportunity,
            submitter_id,
            team_id
        ),
        match_flow_kwargs={
            "amount": opportunity.total_amount,
            "license_type": opportunity.license_type.value,
        },
        submitter_id=submitter_id,
        submitter_name=submitter_name,
        team_id=team_id,
        rollback_on_no_flow=True,
    )

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "商机创建失败"
        )

    opportunity_crud.log_created(db, entity, submitter_id, team_id)
    await _trigger_opportunity_intelligence_refresh(
        db,
        _build_opportunity_intelligence_change(
            entity,
            change_type="created",
            actor_id=submitter_id,
        ),
    )
    return OpportunityResponse(**_opportunity_response_dict(db, entity, team_id))


@router.get("/", response_model=PaginatedResponse[OpportunityListResponse], summary="查询商机列表", description="支持分页、按状态/阶段/负责人等多条件筛选和动态排序，返回客户名称、采购阶段、负责人信息")
def get_opportunities(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    opportunity_status: Optional[str] = Query(None, alias="status", description="商机状态：0:跟进中, 1:已赢单, 2:已输单，多个值用逗号分隔"),
    status_exclude: Optional[str] = Query(None, description="排除的商机状态，多个值用逗号分隔"),
    stage_id: int = Query(None, description="采购阶段ID（已废弃，保留用于兼容）"),
    owner_id: str = Query(None, description="负责人ID"),
    owner_id_exclude: Optional[str] = Query(None, description="排除的负责人ID，多个值用逗号分隔"),
    customer_id: Optional[str] = Query(None, description="客户对外ID"),
    keyword: str = Query(None, description="关键词搜索"),
    search: Optional[str] = Query(None, description="统一搜索，可搜索商机名称、客户或阶段"),
    customer_keyword: str = Query(None, description="客户名称关键词"),
    license_type: str = Query(None, description="授权模式"),
    license_type_exclude: Optional[str] = Query(None, description="排除的授权模式，多个值用逗号分隔"),
    purchase_type: str = Query(None, description="采购类型"),
    purchase_type_exclude: Optional[str] = Query(None, description="排除的采购类型，多个值用逗号分隔"),
    stage_name: str = Query(None, description="销售阶段名称"),
    expected_closing_date_start: date = Query(None, description="预计成交日期起始"),
    expected_closing_date_end: date = Query(None, description="预计成交日期结束"),
    order_by: str = Query(None, description="排序字段"),
    order_dir: str = Query(None, description="排序方向（asc/desc）"),
    filters: Optional[str] = Query(None, description="通用筛选条件 JSON"),
    sorts: Optional[str] = Query(None, description="通用排序条件 JSON"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text

    from app.crud.permission import permission_crud

    # 获取用户权限码
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有 view:all 权限
    has_view_all = "opportunity:view:all" in permission_codes

    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    internal_customer_id = None
    if customer_id is not None:
        customer = check_customer_view_permission(customer_id, team_id, current_user, db)
        internal_customer_id = customer.id

    if uses_unified_list_query(filters=parsed_filters, sorts=parsed_sorts):
        actual_owner_id = enforce_owner_view_scope(
            parsed_filters or [],
            current_user_id=str(current_user.id),
            has_view_all=has_view_all,
            permission_detail="只能查看自己负责的商机，或需要 opportunity:view:all 权限查看他人数据",
            default_to_self=customer_id is None,
        )
    else:
        actual_owner_id = owner_id
        requested_owner_ids = [item.strip() for item in actual_owner_id.split(",") if item.strip()] if actual_owner_id else []
        if requested_owner_ids and any(item != str(current_user.id) for item in requested_owner_ids) and not has_view_all:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能查看自己负责的商机，或需要 opportunity:view:all 权限查看他人数据"
            )
        if customer_id is not None:
            actual_owner_id = None
        elif actual_owner_id is None and not has_view_all:
            actual_owner_id = str(current_user.id)

    opportunities, total = run_or_400(lambda: opportunity_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        status=opportunity_status,
        status_exclude=status_exclude,
        stage_id=stage_id,
        owner_id=actual_owner_id,
        owner_id_exclude=owner_id_exclude,
        customer_id=internal_customer_id,
        keyword=keyword,
        search=search,
        customer_keyword=customer_keyword,
        license_type=license_type,
        license_type_exclude=license_type_exclude,
        purchase_type=purchase_type,
        purchase_type_exclude=purchase_type_exclude,
        stage_name=stage_name,
        expected_closing_date_start=expected_closing_date_start,
        expected_closing_date_end=expected_closing_date_end,
        order_by=order_by,
        order_dir=order_dir,
        filters=parsed_filters,
        sorts=parsed_sorts,
    ))
    
    result = []
    journey_public_ids = _deal_journey_public_id_map(
        db,
        team_id=team_id,
        journey_ids=[opp.deal_journey_id for opp in opportunities],
    )
    for opp in opportunities:
        customer = customer_crud.get_by_id(db, opp.customer_id, team_id)
        
        owner_info = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :owner_id
        """), {"owner_id": int(opp.owner_id)}).first()
        
        stage = None
        stage_info = None
        if opp.current_stage_snapshot_id:
            snapshot_data = db.execute(text("""
                SELECT id, stage_name, win_probability, template_sort_order
                FROM crm_opportunity_stage_snapshots
                WHERE id = :snapshot_id
            """), {"snapshot_id": opp.current_stage_snapshot_id}).first()
            
            if snapshot_data:
                stage = {
                    "id": snapshot_data[0],
                    "stage_code": "",
                    "stage_name": snapshot_data[1],
                    "win_probability": snapshot_data[2],
                    "sort_order": snapshot_data[3],
                    "description": None,
                    "is_active": 1,
                    "created_time": opp.created_time,
                    "last_modified_time": opp.last_modified_time
                }
                stage_info = {
                    "id": snapshot_data[0],
                    "stage_name": snapshot_data[1],
                    "win_probability": snapshot_data[2],
                    "is_default": 0,
                }
        
        opp_dict = {
            "id": opp.public_id,
            "public_id": opp.public_id,
            "deal_journey_id": journey_public_ids.get(opp.deal_journey_id) if opp.deal_journey_id else None,
            "opportunity_number": opp.opportunity_number,
            "opportunity_name": opp.opportunity_name,
            "customer_id": customer.public_id if customer else None,
            "total_amount": float(opp.total_amount),
            "user_count": opp.user_count,
            "unit_price": float(opp.unit_price),
            "license_type": opp.license_type,
            "subscription_years": opp.subscription_years,
            "purchase_type": opp.purchase_type,
            "decision_maker_count": opp.decision_maker_count,
            "expected_closing_date": opp.expected_closing_date,
            "stage_id": opp.procurement_stage_id,
            "win_probability": opp.win_probability,
            "owner_id": opp.owner_id,
            "status": opp.status,
            "approval_phase": _resolve_opportunity_approval_phase(db, opp, team_id),
            "loss_reason": opp.loss_reason,
            "actual_amount": float(opp.actual_amount) if opp.actual_amount else None,
            "actual_closing_date": opp.actual_closing_date,
            "creator_id": opp.creator_id,
            "created_time": opp.created_time,
            "last_modified_time": opp.last_modified_time,
            "version": opp.version,
            "customer_name": customer.account_name if customer else None,
            "stage": stage,
            "stage_info": stage_info,
            "owner_info": {
                "id": str(owner_info[0]),
                "name": owner_info[1],
                "avatar_url": owner_info[2]
            } if owner_info else None
        }
        opp_dict.update(_opportunity_product_payload(opp))
        
        result.append(OpportunityListResponse(**opp_dict))
    
    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[OpportunityListResponse](
        items=result,
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


def _build_opportunity_list_responses(projection_db, opportunities, team_id: int) -> List[OpportunityListResponse]:
    """Batch-project opportunity ORM rows into list responses with display info."""
    from sqlalchemy import text

    result = []
    journey_public_ids = _deal_journey_public_id_map(
        projection_db,
        team_id=team_id,
        journey_ids=[opp.deal_journey_id for opp in opportunities],
    )
    owner_ids = {int(opp.owner_id) for opp in opportunities if opp.owner_id}
    users_info = {}
    if owner_ids:
        placeholders = ','.join(f':owner_{i}' for i in range(len(owner_ids)))
        rows = projection_db.execute(text(f"""
            SELECT id, name, avatar_url FROM users WHERE id IN ({placeholders})
        """), {f'owner_{i}': uid for i, uid in enumerate(owner_ids)}).fetchall()
        users_info = {str(row[0]): {"id": str(row[0]), "name": row[1], "avatar_url": row[2]} for row in rows}

    snapshot_ids = {opp.current_stage_snapshot_id for opp in opportunities if opp.current_stage_snapshot_id}
    snapshots = {}
    if snapshot_ids:
        placeholders = ','.join(f':snap_{i}' for i in range(len(snapshot_ids)))
        rows = projection_db.execute(text(f"""
            SELECT id, stage_name, win_probability, template_sort_order
            FROM crm_opportunity_stage_snapshots WHERE id IN ({placeholders})
        """), {f'snap_{i}': sid for i, sid in enumerate(snapshot_ids)}).fetchall()
        snapshots = {row[0]: row for row in rows}

    customer_ids = {opp.customer_id for opp in opportunities if opp.customer_id}
    customers = {}
    if customer_ids:
        from app.models.customer import Customer

        customers_list = (
            projection_db.query(Customer)
            .filter(Customer.team_id == team_id, Customer.id.in_(customer_ids))
            .all()
        )
        customers = {c.id: c for c in customers_list}
    product_payloads = _opportunity_product_payloads(projection_db, opportunities)
    empty_product_payload = _opportunity_product_payload(None)


    for opp in opportunities:
        customer = customers.get(opp.customer_id)
        snapshot_data = snapshots.get(opp.current_stage_snapshot_id) if opp.current_stage_snapshot_id else None
        stage = None
        stage_info = None
        if snapshot_data:
            stage = {
                "id": snapshot_data[0],
                "stage_code": "",
                "stage_name": snapshot_data[1],
                "win_probability": snapshot_data[2],
                "sort_order": snapshot_data[3],
                "description": None,
                "is_active": 1,
                "created_time": opp.created_time,
                "last_modified_time": opp.last_modified_time
            }
            stage_info = {
                "id": snapshot_data[0],
                "stage_name": snapshot_data[1],
                "win_probability": snapshot_data[2],
                "is_default": 0,
            }

        opp_dict = {
            "id": opp.public_id,
            "public_id": opp.public_id,
            "deal_journey_id": journey_public_ids.get(opp.deal_journey_id) if opp.deal_journey_id else None,
            "opportunity_number": opp.opportunity_number,
            "opportunity_name": opp.opportunity_name,
            "customer_id": customer.public_id if customer else None,
            "total_amount": float(opp.total_amount),
            "user_count": opp.user_count,
            "unit_price": float(opp.unit_price),
            "license_type": opp.license_type,
            "subscription_years": opp.subscription_years,
            "purchase_type": opp.purchase_type,
            "decision_maker_count": opp.decision_maker_count,
            "expected_closing_date": opp.expected_closing_date,
            "stage_id": opp.procurement_stage_id,
            "win_probability": opp.win_probability,
            "owner_id": opp.owner_id,
            "status": opp.status,
            "approval_phase": _resolve_opportunity_approval_phase(projection_db, opp, team_id),
            "loss_reason": opp.loss_reason,
            "actual_amount": float(opp.actual_amount) if opp.actual_amount else None,
            "actual_closing_date": opp.actual_closing_date,
            "creator_id": opp.creator_id,
            "created_time": opp.created_time,
            "last_modified_time": opp.last_modified_time,
            "version": opp.version,
            "customer_name": customer.account_name if customer else None,
            "stage": stage,
            "stage_info": stage_info,
            "owner_info": users_info.get(str(opp.owner_id)),
        }
        opp_dict.update(product_payloads.get(opp.id, empty_product_payload))
        result.append(OpportunityListResponse(**opp_dict))

    return result


def _opportunity_export_row(item: OpportunityListResponse) -> dict[str, object]:
    return {
        "public_id": item.public_id,
        "opportunity_name": item.opportunity_name,
        "owner": item.owner_info.name if item.owner_info else None,
        "customer_name": item.customer_name,
        "product_name": item.product_name,
        "total_amount": item.total_amount,
        "user_count": item.user_count,
        "license_type": LICENSE_TYPE_LABELS.get(item.license_type, item.license_type),
        "purchase_type": PURCHASE_TYPE_LABELS.get(item.purchase_type, item.purchase_type),
        "expected_closing_date": item.expected_closing_date,
        "stage": item.stage.stage_name if item.stage else None,
        "win_probability": item.win_probability,
        "status": OPPORTUNITY_STATUS_LABELS.get(item.status, str(item.status)),
        "approval_phase": APPROVAL_PHASE_LABELS.get(item.approval_phase, item.approval_phase) if item.approval_phase else None,
        "created_time": item.created_time,
    }


def _iter_opportunity_export_rows(stream, team_id: int, projection_session_factory=SessionLocal) -> Iterator[dict[str, object]]:
    for batch in iter_batches(stream, 500):
        projection_db = projection_session_factory()
        try:
            for item in _build_opportunity_list_responses(projection_db, batch, team_id):
                yield _opportunity_export_row(item)
        finally:
            projection_db.close()


@router.post(
    "/export",
    dependencies=[Depends(require_permission("opportunity:export"))],
    summary="导出商机列表",
    description="按当前筛选条件导出全部匹配商机为 Excel",
)
def export_opportunities(
    request: OpportunityListExportRequest,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    from app.crud.permission import permission_crud

    permission_codes = {
        p.code
        for p in permission_crud.get_user_permissions(db, current_user.id, team_id)
    }
    has_view_all = "opportunity:view:all" in permission_codes
    owner_id = enforce_owner_view_scope(
        request.filters,
        current_user_id=str(current_user.id),
        has_view_all=has_view_all,
        permission_detail="只能查看自己负责的商机，或需要 opportunity:view:all 权限查看他人数据",
    )

    status_value = {"active": "0", "won": "1", "lost": "2"}.get(request.tab)
    query = run_or_400(lambda: opportunity_crud.build_list_query(
        db,
        team_id=team_id,
        status=status_value,
        owner_id=owner_id,
        search=request.search,
        filters=request.filters,
        sorts=request.sorts,
    ))
    stream = query.enable_eagerloads(False).execution_options(stream_results=True).yield_per(500)
    rows = _iter_opportunity_export_rows(stream, team_id, projection_session_factory=SessionLocal)
    generated = run_list_export_or_400(lambda: create_list_export_file(
        catalog=OPPORTUNITIES_LIST_EXPORT_CATALOG,
        selected_keys=request.fields,
        rows=rows,
        file_stem="商机列表-全部商机" if request.tab == "all" else f"商机列表-{OPPORTUNITY_STATUS_LABELS[int(status_value)]}",
    ))
    return list_export_file_response(generated)


@router.get("/available-for-contract", response_model=List[OpportunityListResponse], summary="获取可创建合同的商机列表", description="""

**功能说明：**
- 获取客户可创建合同的商机
- 只返回"已赢单"（status=1）的商机
- 排除已经创建合同的商机
- 不需要分页，返回所有符合条件的商机

**业务场景：**
- 创建合同时，在商机下拉框中选择
- 避免选择已输单的商机
- 避免重复创建合同

**路径参数：**
- customer_id: 客户对外ID（必填）

**业务规则：**
- 只返回已赢单（status=1）的商机
- 排除已经有关联合同的商机（opportunity_id在contracts表中存在）
- 不需要分页，返回所有符合条件的商机

**返回字段：**
- 商机基本信息：对外ID、名称、实际金额等
- 当前阶段信息：阶段名称、赢率
- 客户信息：客户名称
- 负责人信息：负责人姓名
""")
def get_available_opportunities_for_contract(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)

    opportunities = opportunity_crud.get_available_for_contract(db, customer.id, team_id)
    result = []
    journey_public_ids = _deal_journey_public_id_map(
        db,
        team_id=team_id,
        journey_ids=[opp.deal_journey_id for opp in opportunities],
    )
    for opp in opportunities:
        customer_info = None
        if opp.customer_id:
            customer = customer_crud.get_by_id(db, opp.customer_id, team_id)
            if customer:
                customer_info = {
                    "id": customer.public_id,
                    "public_id": customer.public_id,
                    "account_name": customer.account_name
                }
        
        owner_info = None
        if opp.owner_id:
            from app.crud.user import user_crud
            owner = user_crud.get_by_id(db, int(opp.owner_id))
            if owner:
                owner_info = {
                    "id": str(owner.id),
                    "name": owner.name,
                    "avatar_url": owner.avatar_url
                }

        creator_info = None
        if opp.creator_id:
            from app.crud.user import user_crud
            creator = user_crud.get_by_id(db, int(opp.creator_id))
            if creator:
                creator_info = {
                    "id": str(creator.id),
                    "name": creator.name,
                    "avatar_url": creator.avatar_url
                }

        result.append(OpportunityListResponse(**{
            "id": opp.public_id,
            "public_id": opp.public_id,
            "deal_journey_id": journey_public_ids.get(opp.deal_journey_id) if opp.deal_journey_id else None,
            "opportunity_number": opp.opportunity_number,
            "opportunity_name": opp.opportunity_name,
            "customer_id": customer_info["id"] if customer_info else None,
            "customer_name": customer_info["account_name"] if customer_info else "",
            "procurement_method_id": opp.procurement_method_id,
            "total_amount": float(opp.total_amount),
            "user_count": opp.user_count,
            "unit_price": float(opp.unit_price),
            "license_type": opp.license_type,
            "subscription_years": opp.subscription_years,
            "purchase_type": opp.purchase_type,
            "decision_maker_count": opp.decision_maker_count,
            "expected_closing_date": opp.expected_closing_date,
            "stage_id": opp.procurement_stage_id,
            "win_probability": opp.win_probability,
            "owner_id": opp.owner_id,
            "status": opp.status,
            "approval_phase": _resolve_opportunity_approval_phase(db, opp, team_id),
            "loss_reason": opp.loss_reason,
            "actual_amount": float(opp.actual_amount) if opp.actual_amount else None,
            "actual_closing_date": opp.actual_closing_date,
            "creator_id": opp.creator_id,
            "created_time": opp.created_time,
            "last_modified_time": opp.last_modified_time,
            "version": opp.version,
            "stage": None,
            "stage_info": None,
            "customer_info": customer_info,
            "owner_info": owner_info,
            "creator_info": creator_info
        }))

    return result


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse, summary="获取商机详情", description="返回商机完整信息及关联的客户、负责人、创建人等信息")
def get_opportunity(
    opportunity_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    opportunity = check_opportunity_view_permission(opportunity_id, team_id, current_user, db)
    return opportunity_detail_response(db, opportunity, team_id)




@router.get("/{opportunity_id}/procurement-stages", response_model=List[OpportunityProcurementStageInfo], summary="获取商机采购阶段", description="获取商机对应的采购方式的所有阶段，标注当前商机的阶段")
def get_opportunity_procurement_stages(
    opportunity_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text

    from app.crud.procurement import procurement_stage_template_crud

    opportunity = check_opportunity_view_permission(opportunity_id, team_id, current_user, db)
    
    if not opportunity.procurement_method_id:
        return []
    
    stages = procurement_stage_template_crud.get_by_method(db, opportunity.procurement_method_id)
    
    result = []
    for stage in stages:
        is_current = False
        if opportunity.current_stage_snapshot_id:
            snapshot_data = db.execute(text("""
                SELECT procurement_stage_template_id
                FROM crm_opportunity_stage_snapshots
                WHERE id = :snapshot_id
            """), {"snapshot_id": opportunity.current_stage_snapshot_id}).first()
            
            if snapshot_data and snapshot_data[0] == stage.id:
                is_current = True
        
        result.append(OpportunityProcurementStageInfo(
            id=stage.id,
            stage_name=stage.stage_name,
            win_probability=stage.win_probability,
            sort_order=stage.sort_order,
            is_current=is_current,
            is_default_start=stage.is_default_start,
            can_skip=stage.can_skip
        ))
    
    return result


@router.put("/{opportunity_id}", response_model=OpportunityResponse, summary="编辑商机", description="更新商机基础信息")
async def update_opportunity(
    opportunity_id: str,
    opportunity: OpportunityUpdate,
    db_opportunity = Depends(check_opportunity_edit_permission),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    _ensure_opportunity_not_pending(db, db_opportunity, db_opportunity.team_id)
    try:
        updated_opportunity = opportunity_crud.update(db, db_opportunity, opportunity)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _trigger_opportunity_intelligence_refresh(
        db,
        _build_opportunity_intelligence_change(
            updated_opportunity,
            change_type="updated",
            actor_id=str(current_user.id),
        ),
    )
    return OpportunityResponse(**_opportunity_response_dict(db, updated_opportunity, db_opportunity.team_id))


@router.patch(
    "/{opportunity_id}/deal-journey",
    response_model=OpportunityResponse,
    summary="调整商机业务旅程关联",
    description="显式关联、迁移或解除商机的业务旅程；不会改写既有合同、回款、跟进和承诺的历史归属。",
)
async def update_opportunity_deal_journey(
    opportunity_id: str,
    journey_update: OpportunityDealJourneyUpdate,
    db_opportunity=Depends(check_opportunity_edit_permission),
    current_user=Depends(get_current_active_user),
    db: Session=Depends(get_db),
):
    _ensure_opportunity_not_pending(db, db_opportunity, db_opportunity.team_id)

    from app.services.deal_journey_service import (
        OpportunityDealJourneyConflictError,
        deal_journey_service,
    )

    resolved_deal_journey_id: int | None = None
    if journey_update.deal_journey_id is not None:
        if not is_deal_journey_public_id(journey_update.deal_journey_id):
            raise HTTPException(status_code=404, detail="业务旅程不存在")
        target = deal_journey_crud.get_by_public_id(
            db,
            journey_update.deal_journey_id,
            db_opportunity.team_id,
            customer_id=db_opportunity.customer_id,
        )
        if target is None:
            raise HTTPException(status_code=404, detail="业务旅程不存在")
        resolved_deal_journey_id = int(target.id)

    try:
        if resolved_deal_journey_id is None:
            deal_journey_service.detach_opportunity(
                db,
                db_opportunity,
                actor_id=str(current_user.id),
                expected_version=journey_update.expected_version,
            )
        else:
            deal_journey_service.associate_opportunity(
                db,
                db_opportunity,
                deal_journey_id=resolved_deal_journey_id,
                actor_id=str(current_user.id),
                expected_version=journey_update.expected_version,
            )
        db.commit()
        db.refresh(db_opportunity)
    except OpportunityDealJourneyConflictError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "OPPORTUNITY_VERSION_CONFLICT",
                "message": str(exc),
                "details": {
                    "opportunity_id": exc.opportunity_id,
                    "expected_version": exc.expected_version,
                    "current_version": exc.current_version,
                },
            },
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # The association_changed event registered by DealJourneyService is the
    # authoritative refresh trigger for this operation. Do not enqueue a
    # second generic opportunity-updated run after commit.
    return OpportunityResponse(**_opportunity_response_dict(db, db_opportunity, db_opportunity.team_id))


@router.post("/{opportunity_id}/move-stage", response_model=OpportunityDetailResponse, summary="推进商机阶段", description="推进商机到下一阶段，使用新的采购阶段模板系统，创建阶段快照")
async def move_opportunity_stage(
    opportunity_id: str,
    stage_move: OpportunityMoveToStage,
    db_opportunity = Depends(check_opportunity_edit_permission),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):

    from sqlalchemy import text

    from app.schemas.opportunity import CurrentStageSnapshotInfo

    _ensure_opportunity_approved(db, db_opportunity, db_opportunity.team_id)

    updated_opportunity = opportunity_crud.move_to_stage(
        db=db,
        opportunity_id=db_opportunity.id,
        target_stage_template_id=stage_move.stage_template_id,
        operator_id=str(current_user.id)
    )
    await _trigger_opportunity_intelligence_refresh(
        db,
        _build_opportunity_intelligence_change(
            updated_opportunity,
            change_type="updated",
            actor_id=str(current_user.id),
        ),
    )
    
    procurement_stage_info = None
    if updated_opportunity.current_stage_snapshot_id:
        snapshot_data = db.execute(text("""
            SELECT 
                s.id,
                s.procurement_stage_template_id,
                s.stage_name,
                s.win_probability,
                s.template_sort_order,
                s.template_code,
                s.entered_at,
                s.exited_at,
                pm.id as procurement_method_id,
                pm.code as procurement_method_code,
                pm.name as procurement_method_name,
                pm.is_active as procurement_method_is_active
            FROM crm_opportunity_stage_snapshots s
            LEFT JOIN crm_procurement_stage_templates pt ON s.procurement_stage_template_id = pt.id
            LEFT JOIN crm_procurement_methods pm ON pt.procurement_method_id = pm.id
            WHERE s.id = :snapshot_id
        """), {"snapshot_id": updated_opportunity.current_stage_snapshot_id}).first()
        
        if snapshot_data:
            from app.schemas.customer import ProcurementMethodInfo
            procurement_method_dict = {
                "id": snapshot_data[8],
                "code": snapshot_data[9],
                "name": snapshot_data[10],
                "is_active": snapshot_data[11]
            } if snapshot_data[8] else None
            
            procurement_stage_info = CurrentStageSnapshotInfo(
                id=snapshot_data[0],
                procurement_stage_template_id=snapshot_data[1],
                stage_name=snapshot_data[2],
                win_probability=snapshot_data[3],
                template_sort_order=snapshot_data[4],
                template_code=snapshot_data[5],
                entered_at=snapshot_data[6],
                exited_at=snapshot_data[7],
                procurement_method=ProcurementMethodInfo(**procurement_method_dict) if procurement_method_dict else None
            )
    
    result = {
        "id": updated_opportunity.public_id,
        "public_id": updated_opportunity.public_id,
        "deal_journey_id": _deal_journey_public_id(
            db, updated_opportunity.deal_journey_id, updated_opportunity.team_id
        ),
        "opportunity_number": updated_opportunity.opportunity_number,
        "opportunity_name": updated_opportunity.opportunity_name,
        "customer_id": _customer_public_id(db, updated_opportunity.customer_id, updated_opportunity.team_id),
        "total_amount": float(updated_opportunity.total_amount),
        "user_count": updated_opportunity.user_count,
        "unit_price": float(updated_opportunity.unit_price),
        "license_type": updated_opportunity.license_type,
        "subscription_years": updated_opportunity.subscription_years,
        "purchase_type": updated_opportunity.purchase_type,
        "decision_maker_count": updated_opportunity.decision_maker_count,
        "expected_closing_date": updated_opportunity.expected_closing_date,
        "stage_id": updated_opportunity.procurement_stage_id,
        "procurement_stage_id": updated_opportunity.procurement_stage_id,
        "win_probability": updated_opportunity.win_probability,
        "owner_id": updated_opportunity.owner_id,
        "status": updated_opportunity.status,
        "approval_phase": _resolve_opportunity_approval_phase(db, updated_opportunity, updated_opportunity.team_id),
        "loss_reason": updated_opportunity.loss_reason,
        "actual_amount": float(updated_opportunity.actual_amount) if updated_opportunity.actual_amount else None,
        "actual_closing_date": updated_opportunity.actual_closing_date,
        "creator_id": updated_opportunity.creator_id,
        "created_time": updated_opportunity.created_time,
        "last_modified_time": updated_opportunity.last_modified_time,
        "updated_time": updated_opportunity.last_modified_time,
        "version": updated_opportunity.version,
        "procurement_method_id": updated_opportunity.procurement_method_id,
        "procurement_method_info": None,
        "current_stage_snapshot": procurement_stage_info,
        "procurement_stages": None,
        "customer_name": None,
        "customer_info": None,
        "owner_info": None,
        "creator_info": None
    }
    result.update(_opportunity_product_payload(updated_opportunity))
    
    return result


@router.patch("/{opportunity_id}/win", response_model=OpportunityResponse, summary="标记赢单", description="状态改为已赢单，记录实际成交金额")
async def mark_opportunity_as_won(
    opportunity_id: str,
    win_data: OpportunityWin,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("opportunity:win")),
    db: Session = Depends(get_db)
):
    db_opportunity = check_opportunity_edit_permission(opportunity_id, team_id, current_user, db)
    _ensure_opportunity_approved(db, db_opportunity, team_id)

    updated_opportunity = opportunity_crud.mark_as_won(db, db_opportunity, win_data, str(current_user.id))
    await _trigger_opportunity_intelligence_refresh(
        db,
        _build_opportunity_intelligence_change(
            updated_opportunity,
            change_type="updated",
            actor_id=str(current_user.id),
        ),
    )

    customer = customer_crud.get_by_id(db, db_opportunity.customer_id, team_id)
    outbound_notification_job_service.queue_committed(
        db,
        team_id=team_id,
        event_type=OutboundNotificationEventType.OPPORTUNITY_WON,
        business_type="OPPORTUNITY",
        business_id=int(updated_opportunity.id),
        recipient_user_ids=[db_opportunity.owner_id],
        actor_id=str(current_user.id),
        payload_json={
            "opportunity_name": db_opportunity.opportunity_name,
            "customer_name": customer.account_name if customer else "",
            "actual_amount": float(win_data.actual_amount),
        },
    )
    return OpportunityResponse(**_opportunity_response_dict(db, updated_opportunity, team_id))


@router.patch("/{opportunity_id}/lose", response_model=OpportunityResponse, summary="标记输单", description="状态改为已输单，必须记录输单原因")
async def mark_opportunity_as_lost(
    opportunity_id: str,
    lose_data: OpportunityLose,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("opportunity:lose")),
    db: Session = Depends(get_db)
):
    db_opportunity = check_opportunity_edit_permission(opportunity_id, team_id, current_user, db)
    _ensure_opportunity_approved(db, db_opportunity, team_id)

    updated_opportunity = opportunity_crud.mark_as_lost(db, db_opportunity, lose_data, str(current_user.id))
    await _trigger_opportunity_intelligence_refresh(
        db,
        _build_opportunity_intelligence_change(
            updated_opportunity,
            change_type="updated",
            actor_id=str(current_user.id),
        ),
    )

    customer = customer_crud.get_by_id(db, db_opportunity.customer_id, team_id)
    outbound_notification_job_service.queue_committed(
        db,
        team_id=team_id,
        event_type=OutboundNotificationEventType.OPPORTUNITY_LOST,
        business_type="OPPORTUNITY",
        business_id=int(updated_opportunity.id),
        recipient_user_ids=[db_opportunity.owner_id],
        actor_id=str(current_user.id),
        payload_json={
            "opportunity_name": db_opportunity.opportunity_name,
            "customer_name": customer.account_name if customer else "",
            "loss_reason": lose_data.loss_reason,
        },
    )
    return OpportunityResponse(**_opportunity_response_dict(db, updated_opportunity, team_id))


@router.delete("/{opportunity_id}", response_model=MessageResponse, summary="删除商机", description="删除商机")
async def delete_opportunity(
    opportunity_id: str,
    db_opportunity = Depends(check_opportunity_delete_permission),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        change = _build_opportunity_intelligence_change(
            db_opportunity,
            change_type="deleted",
            actor_id=str(current_user.id),
        )
        opportunity_crud.delete(db, db_opportunity.id)
        await _trigger_opportunity_intelligence_refresh(
            db,
            change,
        )
        return MessageResponse(message="删除成功")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


analytics_router = APIRouter(prefix="/v1/analytics", tags=["商机分析"])


@analytics_router.get("/sales-funnel", response_model=List[SalesFunnelResponse], summary="获取销售漏斗", description="返回各阶段的商机数量、金额汇总、平均赢率，用于可视化漏斗图")
def get_sales_funnel(
    owner_id: str = Query(None, description="负责人ID"),
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime

    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    return opportunity_crud.get_sales_funnel(
        db=db,
        team_id=team_id,
        owner_id=owner_id,
        start_date=start_date_obj,
        end_date=end_date_obj
    )


@analytics_router.get("/stage-duration", response_model=List[StageDurationResponse], summary="商机阶段耗时分析", description="分析商机在各阶段平均停留时长，帮助识别瓶颈")
def get_stage_duration(
    owner_id: str = Query(None, description="负责人ID"),
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime

    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    return opportunity_crud.get_stage_duration(
        db=db,
        team_id=team_id,
        owner_id=owner_id,
        start_date=start_date_obj,
        end_date=end_date_obj
    )
