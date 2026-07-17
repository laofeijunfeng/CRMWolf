from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_permission, get_current_user_team, check_opportunity_edit_permission, check_opportunity_delete_permission
from app.crud.opportunity import opportunity_crud, opportunity_stage_crud
from app.crud.customer import customer_crud
from app.schemas.opportunity import (
    OpportunityStageCreate,
    OpportunityStageUpdate,
    OpportunityStageResponse,
    OpportunityCreate,
    OpportunityUpdate,
    OpportunityResponse,
    OpportunityDetailResponse,
    OpportunityListResponse,
    OpportunityStageUpdate as OpportunityStageUpdateRequest,
    OpportunityWin,
    OpportunityLose,
    MessageResponse,
    SalesFunnelResponse,
    StageDurationResponse,
    AnalyticsFilter,
    OpportunityMoveToStage,
    OpportunityProcurementStageInfo
)
from app.services.feishu import feishu_service


router = APIRouter(prefix="/v1/opportunities", tags=["商机管理"])




@router.post("/", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED, summary="创建商机", description="为指定客户创建商机")
def create_opportunity(
    opportunity: OpportunityCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("opportunity:create")),
    db: Session = Depends(get_db)
):
    customer = customer_crud.get_by_id(db, opportunity.customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    return opportunity_crud.create(db, opportunity, str(current_user.id), team_id)


@router.get("/", response_model=List[OpportunityListResponse], summary="查询商机列表", description="支持分页、按状态/阶段/负责人等多条件筛选和动态排序，返回客户名称、采购阶段、负责人信息")
def get_opportunities(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    opportunity_status: Optional[str] = Query(None, alias="status", description="商机状态：0:跟进中, 1:已赢单, 2:已输单，多个值用逗号分隔"),
    status_exclude: Optional[str] = Query(None, description="排除的商机状态，多个值用逗号分隔"),
    stage_id: int = Query(None, description="采购阶段ID（已废弃，保留用于兼容）"),
    owner_id: str = Query(None, description="负责人ID"),
    owner_id_exclude: Optional[str] = Query(None, description="排除的负责人ID，多个值用逗号分隔"),
    customer_id: int = Query(None, description="客户ID"),
    keyword: str = Query(None, description="关键词搜索"),
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
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    from app.models.user import User
    from app.crud.permission import permission_crud

    # 获取用户权限码
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有 view:all 权限
    has_view_all = "opportunity:view:all" in permission_codes

    # 权限验证：如果指定了其他人的 owner_id，必须有 view:all 权限
    actual_owner_id = owner_id
    requested_owner_ids = [item.strip() for item in actual_owner_id.split(",") if item.strip()] if actual_owner_id else []
    if requested_owner_ids and any(item != str(current_user.id) for item in requested_owner_ids):
        if not has_view_all:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能查看自己负责的商机，或需要 opportunity:view:all 权限查看他人数据"
            )

    # 如果前端未指定 owner_id 且没有 view:all 权限，则限制为只看自己的商机
    if actual_owner_id is None and not has_view_all:
        actual_owner_id = str(current_user.id)

    opportunities, _ = opportunity_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        status=opportunity_status,
        status_exclude=status_exclude,
        stage_id=stage_id,
        owner_id=actual_owner_id,
        owner_id_exclude=owner_id_exclude,
        customer_id=customer_id,
        keyword=keyword,
        customer_keyword=customer_keyword,
        license_type=license_type,
        license_type_exclude=license_type_exclude,
        purchase_type=purchase_type,
        purchase_type_exclude=purchase_type_exclude,
        stage_name=stage_name,
        expected_closing_date_start=expected_closing_date_start,
        expected_closing_date_end=expected_closing_date_end,
        order_by=order_by,
        order_dir=order_dir
    )
    
    result = []
    for opp in opportunities:
        customer = customer_crud.get_by_id(db, opp.customer_id, team_id)
        
        owner_info = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :owner_id
        """), {"owner_id": int(opp.owner_id)}).first()
        
        stage_info = None
        if opp.current_stage_snapshot_id:
            snapshot_data = db.execute(text("""
                SELECT id, stage_name, win_probability, template_sort_order
                FROM crm_opportunity_stage_snapshots
                WHERE id = :snapshot_id
            """), {"snapshot_id": opp.current_stage_snapshot_id}).first()
            
            if snapshot_data:
                stage_info = {
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
        
        opp_dict = {
            "id": opp.id,
            "opportunity_name": opp.opportunity_name,
            "customer_id": opp.customer_id,
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
            "loss_reason": opp.loss_reason,
            "actual_amount": float(opp.actual_amount) if opp.actual_amount else None,
            "actual_closing_date": opp.actual_closing_date,
            "creator_id": opp.creator_id,
            "created_time": opp.created_time,
            "last_modified_time": opp.last_modified_time,
            "version": opp.version,
            "customer_name": customer.account_name if customer else None,
            "stage": stage_info,
            "owner_info": {
                "id": str(owner_info[0]),
                "name": owner_info[1],
                "avatar_url": owner_info[2]
            } if owner_info else None
        }
        
        result.append(OpportunityListResponse(**opp_dict))
    
    return result


@router.get("/available-for-contract", response_model=List[OpportunityListResponse], summary="获取可创建合同的商机列表", description="""
获取指定客户的可创建合同的商机列表，只返回"已赢单"且"未创建合同"的商机。

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
- customer_id: 客户ID（必填）

**业务规则：**
- 只返回已赢单（status=1）的商机
- 排除已经有关联合同的商机（opportunity_id在contracts表中存在）
- 不需要分页，返回所有符合条件的商机

**返回字段：**
- 商机基本信息：ID、名称、实际金额等
- 当前阶段信息：阶段名称、赢率
- 客户信息：客户名称
- 负责人信息：负责人姓名
""")
def get_available_opportunities_for_contract(
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

    opportunities = opportunity_crud.get_available_for_contract(db, customer_id, team_id)
    
    result = []
    for opp in opportunities:
        customer_info = None
        if opp.customer_id:
            customer = customer_crud.get_by_id(db, opp.customer_id, team_id)
            if customer:
                customer_info = {
                    "id": customer.id,
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
            "id": opp.id,
            "opportunity_name": opp.opportunity_name,
            "customer_id": opp.customer_id,
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
            "loss_reason": opp.loss_reason,
            "actual_amount": float(opp.actual_amount) if opp.actual_amount else None,
            "actual_closing_date": opp.actual_closing_date,
            "creator_id": opp.creator_id,
            "created_time": opp.created_time,
            "last_modified_time": opp.last_modified_time,
            "version": opp.version,
            "customer_info": customer_info,
            "owner_info": owner_info,
            "creator_info": creator_info
        }))

    return result


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse, summary="获取商机详情", description="返回商机完整信息及关联的客户、负责人、创建人等信息")
def get_opportunity(
    opportunity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    from app.schemas.opportunity import CurrentStageSnapshotInfo
    from app.schemas.customer import ProcurementMethodInfo

    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    customer = customer_crud.get_by_id(db, opportunity.customer_id, team_id)
    
    owner_info = db.execute(text("""
        SELECT id, name, avatar_url
        FROM users
        WHERE id = :owner_id
    """), {"owner_id": int(opportunity.owner_id)}).first()

    creator_info = db.execute(text("""
        SELECT id, name, avatar_url
        FROM users
        WHERE id = :creator_id
    """), {"creator_id": int(opportunity.creator_id)}).first()
    
    procurement_stage_info = None
    if opportunity.current_stage_snapshot_id:
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
        """), {"snapshot_id": opportunity.current_stage_snapshot_id}).first()
        
        if snapshot_data:
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
        "id": opportunity.id,
        "opportunity_name": opportunity.opportunity_name,
        "customer_id": opportunity.customer_id,
        "procurement_method_id": opportunity.procurement_method_id,
        "procurement_method_info": None,
        "total_amount": float(opportunity.total_amount),
        "user_count": opportunity.user_count,
        "unit_price": float(opportunity.unit_price),
        "license_type": opportunity.license_type,
        "subscription_years": opportunity.subscription_years,
        "purchase_type": opportunity.purchase_type,
        "decision_maker_count": opportunity.decision_maker_count,
        "expected_closing_date": opportunity.expected_closing_date,
        "stage_id": opportunity.procurement_stage_id,
        "win_probability": opportunity.win_probability,
        "owner_id": opportunity.owner_id,
        "status": opportunity.status,
        "loss_reason": opportunity.loss_reason,
        "actual_amount": float(opportunity.actual_amount) if opportunity.actual_amount else None,
        "actual_closing_date": opportunity.actual_closing_date,
        "creator_id": opportunity.creator_id,
        "created_time": opportunity.created_time,
        "last_modified_time": opportunity.last_modified_time,
        "version": opportunity.version,
        "current_stage_snapshot": procurement_stage_info,
        "procurement_stages": None,
        'customer_name': customer.account_name if customer else None,
        'customer_info': {
            "id": customer.id,
            "account_name": customer.account_name,
            "industry": customer.industry,
            "city": customer.city,
            "address": customer.address,
            "company_scale": customer.company_scale,
            "status": customer.status,
            "owner_id": customer.owner_id
        } if customer else None,
        'owner_info': {
            "id": str(owner_info[0]),
            "name": owner_info[1],
            "avatar_url": owner_info[2]
        } if owner_info else None,
        'creator_info': {
            "id": str(creator_info[0]),
            "name": creator_info[1],
            "avatar_url": creator_info[2]
        } if creator_info else None
    }
    
    return result




@router.get("/{opportunity_id}/procurement-stages", response_model=List[OpportunityProcurementStageInfo], summary="获取商机采购阶段", description="获取商机对应的采购方式的所有阶段，标注当前商机的阶段")
def get_opportunity_procurement_stages(
    opportunity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    from app.crud.procurement import procurement_stage_template_crud

    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )
    
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
def update_opportunity(
    opportunity_id: int,
    opportunity: OpportunityUpdate,
    db_opportunity = Depends(check_opportunity_edit_permission),
    db: Session = Depends(get_db)
):
    return opportunity_crud.update(db, db_opportunity, opportunity)


@router.post("/{opportunity_id}/move-stage", response_model=OpportunityDetailResponse, summary="推进商机阶段", description="推进商机到下一阶段，使用新的采购阶段模板系统，创建阶段快照")
async def move_opportunity_stage(
    opportunity_id: int,
    stage_move: OpportunityMoveToStage,
    db_opportunity = Depends(check_opportunity_edit_permission),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    from app.schemas.opportunity import CurrentStageSnapshotInfo
    from datetime import datetime

    updated_opportunity = opportunity_crud.move_to_stage(
        db=db,
        opportunity_id=opportunity_id,
        target_stage_template_id=stage_move.stage_template_id,
        operator_id=str(current_user.id)
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
        "id": updated_opportunity.id,
        "opportunity_name": updated_opportunity.opportunity_name,
        "customer_id": updated_opportunity.customer_id,
        "total_amount": float(updated_opportunity.total_amount),
        "user_count": updated_opportunity.user_count,
        "unit_price": float(updated_opportunity.unit_price),
        "license_type": updated_opportunity.license_type,
        "subscription_years": updated_opportunity.subscription_years,
        "purchase_type": updated_opportunity.purchase_type,
        "decision_maker_count": updated_opportunity.decision_maker_count,
        "expected_closing_date": updated_opportunity.expected_closing_date,
        "stage_id": updated_opportunity.procurement_stage_id,
        "win_probability": updated_opportunity.win_probability,
        "owner_id": updated_opportunity.owner_id,
        "status": updated_opportunity.status,
        "loss_reason": updated_opportunity.loss_reason,
        "actual_amount": float(updated_opportunity.actual_amount) if updated_opportunity.actual_amount else None,
        "actual_closing_date": updated_opportunity.actual_closing_date,
        "creator_id": updated_opportunity.creator_id,
        "created_time": updated_opportunity.created_time,
        "last_modified_time": updated_opportunity.last_modified_time,
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
    
    return result


@router.patch("/{opportunity_id}/win", response_model=OpportunityResponse, summary="标记赢单", description="状态改为已赢单，记录实际成交金额")
async def mark_opportunity_as_won(
    opportunity_id: int,
    win_data: OpportunityWin,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("opportunity:win")),
    db: Session = Depends(get_db)
):
    db_opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not db_opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    updated_opportunity = opportunity_crud.mark_as_won(db, db_opportunity, win_data, str(current_user.id))

    customer = customer_crud.get_by_id(db, db_opportunity.customer_id, team_id)
    
    await feishu_service.notify_opportunity_won(
        db_opportunity.owner_id,
        db_opportunity.opportunity_name,
        win_data.actual_amount,
        customer.account_name if customer else None
    )
    
    return updated_opportunity


@router.patch("/{opportunity_id}/lose", response_model=OpportunityResponse, summary="标记输单", description="状态改为已输单，必须记录输单原因")
async def mark_opportunity_as_lost(
    opportunity_id: int,
    lose_data: OpportunityLose,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("opportunity:lose")),
    db: Session = Depends(get_db)
):
    db_opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not db_opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    updated_opportunity = opportunity_crud.mark_as_lost(db, db_opportunity, lose_data, str(current_user.id))

    customer = customer_crud.get_by_id(db, db_opportunity.customer_id, team_id)
    
    await feishu_service.notify_opportunity_lost(
        db_opportunity.owner_id,
        db_opportunity.opportunity_name,
        lose_data.loss_reason,
        customer.account_name if customer else None
    )
    
    return updated_opportunity


@router.delete("/{opportunity_id}", response_model=MessageResponse, summary="删除商机", description="删除商机")
def delete_opportunity(
    opportunity_id: int,
    db_opportunity = Depends(check_opportunity_delete_permission),
    db: Session = Depends(get_db)
):
    try:
        opportunity_crud.delete(db, opportunity_id)
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
