from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import (
    get_current_active_user,
    get_current_user_team,
    check_customer_edit_permission,
    check_customer_view_permission,
)
from app.crud.customer_follow_up import customer_follow_up_crud
from app.schemas.customer_follow_up import (
    CustomerFollowUpCreate,
    CustomerFollowUpUpdate,
    CustomerFollowUpResponse,
    MessageResponse
)


router = APIRouter(prefix="/v1/customer-follow-ups", tags=["客户跟进"])


@router.post("/{customer_id}", response_model=CustomerFollowUpResponse, status_code=status.HTTP_201_CREATED, summary="创建跟进记录", description="为指定客户创建新的跟进记录")
def create_follow_up(
    customer_id: int,
    follow_up: CustomerFollowUpCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    check_customer_edit_permission(customer_id, team_id, current_user, db)

    return customer_follow_up_crud.create(
        db=db,
        obj_in=follow_up,
        customer_id=customer_id,
        creator_id=str(current_user.id),
        team_id=team_id,
        operator_name=current_user.name
    )


@router.get("/{customer_id}", response_model=List[CustomerFollowUpResponse], summary="查询跟进列表", description="获取客户的所有跟进记录，返回跟进人和客户信息")
def get_follow_ups(
    customer_id: int,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text

    check_customer_view_permission(customer_id, team_id, current_user, db)

    follow_ups, total = customer_follow_up_crud.get_by_customer_id(
        db=db,
        customer_id=customer_id,
        skip=skip,
        limit=limit
    )

    result = []
    for follow_up in follow_ups:
        creator_info = None
        if follow_up.creator_id:
            creator_data = db.execute(text("""
                SELECT id, name, avatar_url
                FROM users
                WHERE id = :creator_id
            """), {"creator_id": int(follow_up.creator_id)}).first()

            if creator_data:
                creator_info = {
                    "id": str(creator_data[0]),
                    "name": creator_data[1],
                    "avatar_url": creator_data[2]
                }

        customer_info = None
        if follow_up.customer_id:
            customer_data = db.execute(text("""
                SELECT id, account_name
                FROM crm_customers
                WHERE id = :customer_id
            """), {"customer_id": follow_up.customer_id}).first()

            if customer_data:
                customer_info = {
                    "id": customer_data[0],
                    "account_name": customer_data[1]
                }

        follow_up_dict = {
            "id": follow_up.id,
            "customer_id": follow_up.customer_id,
            "original_lead_id": follow_up.original_lead_id,
            "content": follow_up.content,
            "method": follow_up.method,
            "next_follow_time": follow_up.next_follow_time,
            "next_action": follow_up.next_action,
            "creator_id": follow_up.creator_id,
            "created_time": follow_up.created_time,
            "creator_info": creator_info,
            "customer_info": customer_info
        }

        result.append(CustomerFollowUpResponse(**follow_up_dict))

    return result


@router.put("/{follow_up_id}", response_model=CustomerFollowUpResponse, summary="更新跟进记录", description="更新跟进记录的内容、方式、下次跟进时间等")
def update_follow_up(
    follow_up_id: int,
    follow_up_update: CustomerFollowUpUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text

    follow_up = customer_follow_up_crud.get_by_id(db, follow_up_id)
    if not follow_up:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="跟进记录不存在"
        )

    check_customer_edit_permission(follow_up.customer_id, team_id, current_user, db)

    # 权限检查：只有创建者可以更新
    if follow_up.creator_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权更新此跟进记录"
        )

    updated_follow_up = customer_follow_up_crud.update(
        db=db,
        db_obj=follow_up,
        obj_in=follow_up_update
    )

    # 构建响应（复用 get_follow_ups 的逻辑）
    creator_info = None
    if updated_follow_up.creator_id:
        creator_data = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :creator_id
        """), {"creator_id": int(updated_follow_up.creator_id)}).first()

        if creator_data:
            creator_info = {
                "id": str(creator_data[0]),
                "name": creator_data[1],
                "avatar_url": creator_data[2]
            }

    customer_info = None
    if updated_follow_up.customer_id:
        customer_data = db.execute(text("""
            SELECT id, account_name
            FROM crm_customers
            WHERE id = :customer_id
        """), {"customer_id": updated_follow_up.customer_id}).first()

        if customer_data:
            customer_info = {
                "id": customer_data[0],
                "account_name": customer_data[1]
            }

    follow_up_dict = {
        "id": updated_follow_up.id,
        "customer_id": updated_follow_up.customer_id,
        "original_lead_id": updated_follow_up.original_lead_id,
        "content": updated_follow_up.content,
        "method": updated_follow_up.method,
        "next_follow_time": updated_follow_up.next_follow_time,
        "next_action": updated_follow_up.next_action,
        "creator_id": updated_follow_up.creator_id,
        "created_time": updated_follow_up.created_time,
        "creator_info": creator_info,
        "customer_info": customer_info
    }

    return CustomerFollowUpResponse(**follow_up_dict)


@router.patch("/{follow_up_id}/next-time", response_model=CustomerFollowUpResponse, summary="更新下次跟进时间", description="修改单条记录的下次跟进时间")
def update_next_time(
    follow_up_id: int,
    next_time: CustomerFollowUpUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    follow_up = customer_follow_up_crud.get_by_id(db, follow_up_id)
    if not follow_up:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="跟进记录不存在"
        )

    check_customer_edit_permission(follow_up.customer_id, team_id, current_user, db)

    if next_time.next_follow_time:
        return customer_follow_up_crud.update_next_time(
            db=db,
            db_obj=follow_up,
            next_follow_time=next_time.next_follow_time
        )

    return follow_up


@router.delete("/{follow_up_id}", response_model=MessageResponse, summary="删除跟进记录", description="删除跟进记录")
def delete_follow_up(
    follow_up_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    follow_up = customer_follow_up_crud.get_by_id(db, follow_up_id)
    if not follow_up:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="跟进记录不存在"
        )

    check_customer_edit_permission(follow_up.customer_id, team_id, current_user, db)

    if follow_up.creator_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除此记录"
        )

    customer_follow_up_crud.delete(db, follow_up)
    return MessageResponse(message="删除成功")
