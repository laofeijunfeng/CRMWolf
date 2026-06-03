"""
AI 解析客户跟进信息接口

用于 MagicWand 魔术棒功能，从自然语言中提取跟进信息
复用 follow_up_parser_service
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user, get_db, get_current_user_team
from app.models.user import User
from app.schemas.customer_ai import CustomerAIParseRequest, CustomerAICreateRequest
from app.services.follow_up_parser import follow_up_parser_service
from app.models.lead import FollowUpMethod  # 跟进方式枚举在 lead.py 中定义


router = APIRouter(prefix="/v1/customers/ai", tags=["AI 客户跟进"])


@router.post("/parse")
async def parse_customer_follow_up(
    request: CustomerAIParseRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    AI 解析客户跟进信息（SSE 流式响应）

    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 解析完成，返回结构化信息
    - error: 错误信息
    """
    async def generate_sse():
        db = SessionLocal()
        try:
            # 构建带客户上下文的消息
            context_message = f"[客户：{request.customer_name}（ID：{request.customer_id}）]\n{request.content}"

            async for event in follow_up_parser_service.parse_follow_up_info_stream(
                db=db,
                user_message=context_message
            ):
                # 添加客户信息到 parsed 事件
                if event["event"] == "parsed":
                    event["customer_id"] = request.customer_id
                    event["customer_name"] = request.customer_name
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_customer_follow_up(
    request: CustomerAICreateRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    从 AI 解析结果创建客户跟进记录（用户确认后提交）

    处理 next_action 和 next_follow_time（相对时间转换为具体日期）
    """
    from app.crud.customer_follow_up import customer_follow_up_crud
    from app.crud.customer import customer_crud
    from app.schemas.customer_follow_up import CustomerFollowUpCreate

    # 获取客户信息并验证团队归属
    customer = customer_crud.get_by_id(db, request.customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在或不属于当前团队"
        )

    # 推断跟进方式
    method_str = "其他"
    method_map = {
        "电话": "电话",
        "微信": "微信",
        "拜访": "拜访",
        "邮件": "邮件"
    }
    if request.method and request.method in method_map:
        method_str = method_map[request.method]

    # 解析下次跟进时间（相对时间 → 具体日期）
    next_follow_time_dt = None
    if request.next_follow_time:
        next_follow_time_dt = follow_up_parser_service.parse_relative_time(
            request.next_follow_time,
            base_date=datetime.now()
        )

    # 创建跟进记录
    follow_up_create = CustomerFollowUpCreate(
        content=request.content,
        method=method_str,
        next_action=request.next_action,
        next_follow_time=next_follow_time_dt
    )

    follow_up = customer_follow_up_crud.create(
        db=db,
        obj_in=follow_up_create,
        customer_id=request.customer_id,
        creator_id=str(current_user.id),
        team_id=customer.team_id,
        operator_name=current_user.name if hasattr(current_user, 'name') else None
    )

    return {
        "id": follow_up.id,
        "customer_id": request.customer_id,
        "content": request.content,
        "method": request.method,
        "next_action": request.next_action,
        "next_follow_time": next_follow_time_dt.isoformat() if next_follow_time_dt else None
    }