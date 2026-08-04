import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    check_customer_activity_permission,
    check_customer_view_permission,
    get_current_active_user,
    get_current_user_team,
)
from app.crud.customer_activity import customer_activity_crud
from app.schemas.customer_activity import (
    CustomerActivityCreate,
    CustomerActivityProcessResponse,
    CustomerActivityResponse,
    CustomerActivityUpdate,
    MessageResponse,
    kind_infos,
)
from app.services.customer_activity_kinds import get_activity_kind_meta
from app.services.customer_activity_processing_service import customer_activity_processing_service


router = APIRouter(prefix="/v1/customer-activities", tags=["客户活动"])


def _loads(value: str | None):
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _build_activity_response(db: Session, activity) -> CustomerActivityResponse:
    creator_info = None
    if activity.creator_id:
        creator_data = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :creator_id
        """), {"creator_id": int(activity.creator_id)}).first()
        if creator_data:
            creator_info = {
                "id": str(creator_data[0]),
                "name": creator_data[1],
                "avatar_url": creator_data[2],
            }

    customer_info = None
    if activity.customer_id:
        customer_data = db.execute(text("""
            SELECT public_id, account_name
            FROM crm_customers
            WHERE id = :customer_id
        """), {"customer_id": activity.customer_id}).first()
        if customer_data:
            customer_info = {
                "id": customer_data[0],
                "public_id": customer_data[0],
                "account_name": customer_data[1],
            }

    original_lead_public_id = None
    if activity.original_lead_id:
        lead_data = db.execute(text("""
            SELECT public_id
            FROM crm_leads
            WHERE id = :lead_id
        """), {"lead_id": activity.original_lead_id}).first()
        original_lead_public_id = lead_data[0] if lead_data else None

    meta = get_activity_kind_meta(activity.activity_kind)
    return CustomerActivityResponse(**{
        "id": activity.id,
        "customer_id": customer_info["id"] if customer_info else None,
        "original_lead_id": original_lead_public_id,
        "deal_journey_id": activity.deal_journey_id,
        "activity_kind": activity.activity_kind,
        "activity_category": meta["category"],
        "activity_label": meta["label"],
        "title": activity.title,
        "source_content": activity.source_content,
        "content_json": _loads(activity.content_json),
        "summary": activity.summary,
        "processing_status": activity.processing_status,
        "processing_error": activity.processing_error,
        "processed_at": activity.processed_at,
        "next_follow_time": activity.next_follow_time,
        "next_follow_time_source": activity.next_follow_time_source,
        "next_action": activity.next_action,
        "occurred_at": activity.occurred_at,
        "creator_id": activity.creator_id,
        "created_time": activity.created_time,
        "updated_time": activity.updated_time,
        "creator_info": creator_info,
        "customer_info": customer_info,
        "effectiveness_score": activity.effectiveness_score,
        "effectiveness_is_valid": activity.effectiveness_is_valid,
        "effectiveness_reason": activity.effectiveness_reason,
        "effectiveness_detail_json": activity.effectiveness_detail_json,
        "effectiveness_status": activity.effectiveness_status,
        "effectiveness_evaluated_time": activity.effectiveness_evaluated_time,
        "effectiveness_error_message": activity.effectiveness_error_message,
    })


@router.get("/kinds", summary="客户活动分类元数据")
def get_activity_kinds():
    return [item.model_dump() for item in kind_infos()]


@router.post("/{customer_id}", response_model=CustomerActivityResponse, status_code=status.HTTP_201_CREATED, summary="创建客户活动")
async def create_activity(
    customer_id: str,
    activity: CustomerActivityCreate,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    customer = check_customer_activity_permission(customer_id, team_id, current_user, db)
    created = customer_activity_crud.create(
        db=db,
        obj_in=activity,
        customer_id=customer.id,
        creator_id=str(current_user.id),
        team_id=team_id,
        operator_name=current_user.name,
    )
    await customer_activity_processing_service.trigger_processing(created.id, team_id)
    return _build_activity_response(db, created)


@router.get("/{customer_id}", response_model=List[CustomerActivityResponse], summary="查询客户活动列表")
def get_activities(
    customer_id: str,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    activities, _ = customer_activity_crud.get_by_customer_id(
        db=db,
        customer_id=customer.id,
        team_id=team_id,
        skip=skip,
        limit=limit,
    )
    return [_build_activity_response(db, item) for item in activities]


@router.put("/{activity_id}", response_model=CustomerActivityResponse, summary="更新客户活动")
async def update_activity(
    activity_id: int,
    activity_update: CustomerActivityUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    activity = customer_activity_crud.get_by_id(db, activity_id, team_id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户活动不存在")
    if activity.creator_id != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权更新此客户活动")
    check_customer_activity_permission(activity.customer_id, team_id, current_user, db)
    updated = customer_activity_crud.update(db, activity, activity_update)
    await customer_activity_processing_service.trigger_processing(updated.id, team_id)
    return _build_activity_response(db, updated)


@router.patch("/{activity_id}/next-time", response_model=CustomerActivityResponse, summary="更新下次跟进时间")
async def update_next_time(
    activity_id: int,
    next_time: CustomerActivityUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    activity = customer_activity_crud.get_by_id(db, activity_id, team_id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户活动不存在")
    check_customer_activity_permission(activity.customer_id, team_id, current_user, db)
    if next_time.next_follow_time:
        updated = customer_activity_crud.update_next_time(db, activity, next_time.next_follow_time)
        customer_activity_crud.update_effectiveness_status(db, updated.id, "GENERATING")
        db.refresh(updated)
        await customer_activity_processing_service.trigger_evaluation(updated.id, team_id)
        return _build_activity_response(db, updated)
    return _build_activity_response(db, activity)


@router.post("/{activity_id}/process", response_model=CustomerActivityProcessResponse, summary="重新整理客户活动")
async def process_activity(
    activity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    activity = customer_activity_crud.get_by_id(db, activity_id, team_id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户活动不存在")
    check_customer_activity_permission(activity.customer_id, team_id, current_user, db)
    await customer_activity_processing_service.trigger_processing(activity.id, team_id)
    return CustomerActivityProcessResponse(message="已开始重新整理")


@router.post("/{activity_id}/evaluate", response_model=CustomerActivityProcessResponse, summary="重新评估客户活动")
async def evaluate_activity(
    activity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    activity = customer_activity_crud.get_by_id(db, activity_id, team_id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户活动不存在")
    check_customer_activity_permission(activity.customer_id, team_id, current_user, db)
    await customer_activity_processing_service.trigger_evaluation(activity.id, team_id)
    return CustomerActivityProcessResponse(message="已开始重新评估")


@router.delete("/{activity_id}", response_model=MessageResponse, summary="删除客户活动")
def delete_activity(
    activity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    activity = customer_activity_crud.get_by_id(db, activity_id, team_id)
    if not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户活动不存在")
    if activity.creator_id != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除此客户活动")
    check_customer_activity_permission(activity.customer_id, team_id, current_user, db)
    customer_activity_crud.delete(db, activity)
    return MessageResponse(message="删除成功")
