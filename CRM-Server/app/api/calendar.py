from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.calendar import calendar_crud
from app.schemas.calendar import (
    CalendarMonthResponse,
    CalendarDateDetailResponse,
    FollowUpParseRequest,
    FollowUpParseResponse,
    FollowUpExecuteRequest,
    FollowUpExecuteResponse,
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


@router.post("/follow-up/parse", response_model=FollowUpParseResponse, summary="解析跟进内容")
async def parse_follow_up(
    request: FollowUpParseRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    解析用户输入的跟进内容

    1. 获取待办上下文
    2. 构建带上下文的 Prompt
    3. 调用 AI 解析
    4. 返回解析结果（actions 数组）
    """
    # 获取上下文
    context = calendar_crud.get_todo_context(
        db, request.todo_type, request.todo_id,
        str(current_user.id), team_id
    )
    if not context:
        raise HTTPException(status_code=404, detail="待办不存在或无权访问")

    # 检查待办类型是否支持
    if request.todo_type in ["opportunity", "payment_plan"]:
        return FollowUpParseResponse(
            actions=[],
            reply_text="商机跟进和回款计划暂不支持 AI 快速跟进，请使用详情页手动添加",
            context=context
        )

    # 构建带上下文的 Prompt
    from app.services.skills.dynamic_prompt_service import dynamic_prompt_service
    from app.services.ai_service import ai_service

    system_prompt = dynamic_prompt_service.build_prompt_with_context(db, context)

    # 调用 AI 解析
    user_message = f"实体名称：{context['entity_info']['name']}\n用户输入：{request.user_input}"

    parsed = await ai_service.parse_intent_with_prompt(
        system_prompt, user_message
    )

    # 返回解析结果
    return FollowUpParseResponse(
        actions=parsed.get("actions", []),
        reply_text=parsed.get("reply_text", ""),
        context=context
    )


@router.post("/follow-up/execute", response_model=FollowUpExecuteResponse, summary="执行跟进操作")
async def execute_follow_up(
    request: FollowUpExecuteRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    执行批量 Action

    按顺序执行 actions 数组中的每个 Action
    """
    from app.services.skills.dynamic_skill_service import dynamic_skill_service
    from app.schemas.calendar import FollowUpExecuteResult

    results = await dynamic_skill_service.execute_actions(
        db,
        request.actions,
        current_user.id,
        str(current_user.id),
        team_id
    )

    # 判断整体是否成功
    all_success = all(r.success for r in results)

    # 组合消息
    messages = [r.message for r in results]
    combined_message = "\n".join(messages) if messages else "执行完成"

    # 转换结果格式
    result_list = [
        FollowUpExecuteResult(
            success=r.success,
            message=r.message,
            data=r.data
        )
        for r in results
    ]

    return FollowUpExecuteResponse(
        success=all_success,
        message=combined_message,
        results=result_list
    )