from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.calendar import calendar_crud
from app.schemas.calendar import (
    CalendarMonthResponse,
    CalendarDateDetailResponse,
    TodoContextResponse,
)


router = APIRouter(prefix="/v1/calendar", tags=["日历"])


@router.get("/todos", response_model=CalendarMonthResponse, summary="获取月度待办统计")
def get_calendar_todos(
    year: int = Query(..., ge=2020, le=2030, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    返回指定月份每天的待办数量统计

    待办类型：
    - lead: 线索跟进（LeadFollowUp.next_follow_time）
    - customer: 客户跟进（CustomerFollowUp.next_follow_time）
    - opportunity: 商机跟进（Opportunity.expected_closing_date）
    - payment: 回款计划（PaymentPlan.due_date）
    """
    todos = calendar_crud.get_month_todos(db, str(current_user.id), team_id, year, month)
    return CalendarMonthResponse(year=year, month=month, todos=todos)


@router.get("/todos/date", response_model=CalendarDateDetailResponse, summary="获取单日待办详情")
def get_date_todos(
    date_str: str = Query(..., alias="date", description="日期，格式：YYYY-MM-DD"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    返回指定日期的所有待办事项详情

    包含四种类型的待办详情列表：
    - lead_follow_ups: 线索跟进详情
    - customer_follow_ups: 客户跟进详情
    - opportunities: 商机跟进详情
    - payment_plans: 回款计划详情
    """
    target_date = date.fromisoformat(date_str)

    lead_todos, customer_todos, opportunity_todos, payment_todos = \
        calendar_crud.get_date_detail_todos(db, str(current_user.id), team_id, target_date)

    total_count = len(lead_todos) + len(customer_todos) + len(opportunity_todos) + len(payment_todos)

    return CalendarDateDetailResponse(
        date=date_str,
        lead_follow_ups=lead_todos,
        customer_follow_ups=customer_todos,
        opportunities=opportunity_todos,
        payment_plans=payment_todos,
        total_count=total_count
    )


@router.get("/todos/{todo_type}/{todo_id}/context", response_model=TodoContextResponse, summary="获取待办上下文")
def get_todo_context(
    todo_type: str,
    todo_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取待办的上下文信息（用于 AI 跟进）

    返回待办的详细信息，包括实体名称、联系人、下次跟进时间等
    """
    context = calendar_crud.get_todo_context(db, todo_type, todo_id, str(current_user.id), team_id)
    if not context:
        raise HTTPException(status_code=404, detail="待办不存在或无权访问")
    return TodoContextResponse(**context)