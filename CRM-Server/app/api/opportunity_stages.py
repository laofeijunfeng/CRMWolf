from fastapi import APIRouter, Depends, HTTPException, status, Path, Query
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User
from app.schemas.procurement import (
    AdvanceStageRequest,
    OpportunityStageSnapshotResponse,
    ProcurementStageTemplateResponse
)
from app.crud.procurement import opportunity_stage_snapshot_crud
from app.crud.opportunity import opportunity_crud
from app.crud.procurement import procurement_stage_template_crud
from app.models.procurement import ProcurementMethod


router = APIRouter(prefix="/v1/opportunities", tags=["商机阶段管理"])


@router.get("/{opportunity_id}/current-stage", response_model=OpportunityStageSnapshotResponse, summary="获取商机当前阶段", description="""
获取商机当前所在的阶段快照信息。

**业务规则：**
- 返回最新的未退出的阶段快照
- 包含阶段名称、赢率、进入时间等信息
""")
def get_opportunity_current_stage(
    opportunity_id: int = Path(..., description="商机ID（路径参数）"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # 验证商机归属
    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商机 {opportunity_id} 不存在或不属于当前团队"
        )

    snapshot = opportunity_stage_snapshot_crud.get_current(db, opportunity_id)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商机 {opportunity_id} 没有当前阶段"
        )
    return snapshot


@router.get("/{opportunity_id}/stage-history", response_model=List[OpportunityStageSnapshotResponse], summary="获取商机阶段历史", description="""
获取商机的所有阶段历史记录。

**业务规则：**
- 按进入时间倒序返回
- 包含已退出的历史阶段
- 显示每个阶段的停留时间
""")
def get_opportunity_stage_history(
    opportunity_id: int = Path(..., description="商机ID（路径参数）"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # 验证商机归属
    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商机 {opportunity_id} 不存在或不属于当前团队"
        )

    history = opportunity_stage_snapshot_crud.get_history(db, opportunity_id)
    return history


@router.get("/{opportunity_id}/available-stages", response_model=List[ProcurementStageTemplateResponse], summary="获取可推进到的阶段", description="""
获取商机可以推进到的阶段列表。

**业务规则：**
- 只返回当前阶段之后的阶段
- 包括允许跳过的阶段
- 按sort_order排序
""")
def get_available_stages(
    opportunity_id: int = Path(..., description="商机ID（路径参数）"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # 检查商机是否存在并验证团队归属
    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商机 {opportunity_id} 不存在或不属于当前团队"
        )

    # 获取可用的阶段
    available = opportunity_stage_snapshot_crud.get_available_stages(db, opportunity_id)
    return available


@router.post("/{opportunity_id}/advance-stage", response_model=OpportunityStageSnapshotResponse, summary="推进商机阶段", description="""
将商机推进到指定的阶段。

**业务规则：**
- 目标阶段必须属于同一采购方式
- 阶段只能向前推进
- 如果目标阶段不允许跳过，需要按顺序推进
- 自动结束当前阶段快照，创建新阶段快照
- 同时更新商机的当前阶段信息

**权限要求：**
- 只有商机负责人或管理员可以推进阶段
""")
def advance_opportunity_stage(
    opportunity_id: int,
    advance_in: AdvanceStageRequest,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # 检查商机是否存在并验证团队归属
    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商机 {opportunity_id} 不存在或不属于当前团队"
        )

    # 权限校验：只有负责人或管理员可以推进
    if opportunity.owner_id != str(current_user.id) and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有商机负责人或管理员可以推进阶段"
        )

    # 获取目标阶段模板
    target_stage = procurement_stage_template_crud.get(db, advance_in.target_stage_template_id)
    if not target_stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"目标阶段模板 {advance_in.target_stage_template_id} 不存在"
        )

    try:
        # 推进阶段
        new_snapshot = opportunity_stage_snapshot_crud.advance_stage(
            db, opportunity_id, target_stage, str(current_user.id)
        )

        # 更新商机的当前阶段信息
        opportunity.procurement_method_id = target_stage.procurement_method_id
        opportunity.current_stage_snapshot_id = new_snapshot.id
        opportunity.current_stage_name = new_snapshot.stage_name
        opportunity.current_win_probability = new_snapshot.win_probability
        opportunity.current_stage_entered_at = new_snapshot.entered_at

        db.commit()
        db.refresh(new_snapshot)

        return new_snapshot

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{opportunity_id}/set-procurement-method", response_model=OpportunityStageSnapshotResponse, summary="设置商机采购方式", description="""
为商机设置采购方式，并自动进入默认起始阶段。

**业务规则：**
- 只能为没有阶段的商机设置采购方式
- 设置后会自动创建默认起始阶段的快照
- 同时更新商机的采购方式字段

**使用场景：**
- 创建商机时没有选择采购方式
- 需要修改商机的采购方式
""")
def set_opportunity_procurement_method(
    opportunity_id: int,
    procurement_method_id: int,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # 检查商机是否存在并验证团队归属
    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"商机 {opportunity_id} 不存在或不属于当前团队"
        )

    # 权限校验
    if opportunity.owner_id != str(current_user.id) and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有商机负责人或管理员可以设置采购方式"
        )

    # 检查采购方式是否存在
    from app.crud.procurement import procurement_method_crud
    procurement_method = procurement_method_crud.get(db, procurement_method_id)
    if not procurement_method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"采购方式 {procurement_method_id} 不存在"
        )

    # 检查是否已有阶段
    existing_snapshot = opportunity_stage_snapshot_crud.get_current(db, opportunity_id)
    if existing_snapshot:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="商机已有阶段，不能修改采购方式。请使用推进阶段功能"
        )

    # 获取默认起始阶段
    default_stage = procurement_stage_template_crud.get_default_stage(
        db, procurement_method_id
    )
    if not default_stage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"采购方式 {procurement_method_id} 没有设置默认起始阶段"
        )

    # 创建阶段快照
    new_snapshot = opportunity_stage_snapshot_crud.create(
        db, opportunity_id, default_stage
    )

    # 更新商机
    opportunity.procurement_method_id = procurement_method_id
    opportunity.current_stage_snapshot_id = new_snapshot.id
    opportunity.current_stage_name = new_snapshot.stage_name
    opportunity.current_win_probability = new_snapshot.win_probability
    opportunity.current_stage_entered_at = new_snapshot.entered_at

    db.commit()
    db.refresh(new_snapshot)

    return new_snapshot
