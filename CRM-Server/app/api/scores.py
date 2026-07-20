"""热力值查询 API

提供线索和客户热力值及计算明细的查询接口。

权限：
- 普通用户可查看自己负责的对象热力值
- TEAM_ADMIN/SALES_DIRECTOR 可查看所有对象热力值
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import (
    get_current_user_team,
    get_current_active_user,
    check_customer_edit_permission,
    check_customer_view_permission,
)
from app.models.lead import Lead
from app.models.score_weight import ScoreDetail
from app.crud.lead import lead_crud
from app.crud.score_detail import score_detail_crud
from app.schemas.score_weight import ScoreResponse, ScoreDetailResponse, get_score_level_info

router = APIRouter(prefix="/v1/scores", tags=["热力值查询"])


def check_lead_access(db: Session, lead_id: int, team_id: int, user_id: str) -> Lead:
    """检查线索访问权限

    - 普通用户只能查看自己负责的线索
    - 管理员/总监可以查看所有线索
    """
    lead = lead_crud.get_by_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    # TODO: 添加权限检查（check_lead_access 已在 leads.py 中定义）
    # 这里简化处理，允许团队成员查看
    return lead


@router.get("/lead/{lead_id}", response_model=ScoreResponse, summary="获取线索热力值")
def get_lead_score(
    lead_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取线索热力值及计算明细

    返回：
    - score：热力值分数（0-100）
    - score_level：热力值等级（高/中/低/危险）
    - updated_at：最后更新时间
    - details：计算明细列表
    """
    lead = check_lead_access(db, lead_id, team_id, str(current_user.id))

    # 获取最近一次计算的明细
    details = score_detail_crud.get_latest_details(db, 'LEAD', lead_id)

    # 构建响应
    level_info = get_score_level_info(lead.score)

    return {
        "score": lead.score,
        "score_level": level_info.level,
        "updated_at": lead.score_updated_at,
        "details": details
    }


@router.get("/customer/{customer_id}", response_model=ScoreResponse, summary="获取客户热力值")
def get_customer_score(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取客户热力值及计算明细

    返回：
    - score：热力值分数（0-100）
    - score_level：热力值等级（高/中/低/危险）
    - updated_at：最后更新时间
    - details：计算明细列表
    """
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)

    # 获取最近一次计算的明细
    details = score_detail_crud.get_latest_details(db, 'CUSTOMER', customer_id)

    # 构建响应
    level_info = get_score_level_info(customer.score)

    return {
        "score": customer.score,
        "score_level": level_info.level,
        "updated_at": customer.score_updated_at,
        "details": details
    }


@router.post("/lead/{lead_id}/refresh", response_model=ScoreResponse, summary="刷新线索热力值")
def refresh_lead_score(
    lead_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """手动刷新线索热力值

    通常不需要手动刷新，系统会自动触发。
    仅用于特殊场景或管理员干预。
    """
    lead = check_lead_access(db, lead_id, team_id, str(current_user.id))

    from app.services.score_service import score_service
    score_service.calculate_lead_score(db, lead_id, team_id)

    # 获取最新明细
    details = score_detail_crud.get_latest_details(db, 'LEAD', lead_id)
    level_info = get_score_level_info(lead.score)

    return {
        "score": lead.score,
        "score_level": level_info.level,
        "updated_at": lead.score_updated_at,
        "details": details
    }


@router.post("/customer/{customer_id}/refresh", response_model=ScoreResponse, summary="刷新客户热力值")
def refresh_customer_score(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """手动刷新客户热力值

    通常不需要手动刷新，系统会自动触发。
    仅用于特殊场景或管理员干预。
    """
    customer = check_customer_edit_permission(customer_id, team_id, current_user, db)

    from app.services.score_service import score_service
    score_service.calculate_customer_score(db, customer_id, team_id)

    # 获取最新明细
    details = score_detail_crud.get_latest_details(db, 'CUSTOMER', customer_id)
    level_info = get_score_level_info(customer.score)

    return {
        "score": customer.score,
        "score_level": level_info.level,
        "updated_at": customer.score_updated_at,
        "details": details
    }


@router.post("/batch-refresh/team", summary="批量刷新团队热力值")
def batch_refresh_team_scores(
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """批量刷新当前团队的所有热力值

    通常用于系统维护或初始化场景。
    """
    from app.services.score_service import score_service

    lead_count = score_service.batch_update_lead_scores(db, team_id)
    customer_count = score_service.batch_update_customer_scores(db, team_id)

    return {
        "message": "团队热力值批量刷新完成",
        "leads_updated": lead_count,
        "customers_updated": customer_count
    }
