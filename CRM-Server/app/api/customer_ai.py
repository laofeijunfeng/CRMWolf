"""
AI 解析客户信息接口

包含两个功能：
1. 客户跟进记录解析（MagicWand 魔术棒功能）- 已有
2. 客户创建解析（AI 智能创建）- 新增
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User

# 已有功能（MagicWand）
from app.schemas.customer_ai import CustomerAIParseRequest, CustomerAICreateRequest
from app.services.follow_up_parser import follow_up_parser_service

# 新增功能（AI 创建客户）
from app.schemas.customer_ai_create import CustomerAICreateParseRequest, CustomerAICreateRequest
from app.services.ai_parser.factory import EntityAIParserFactory


router = APIRouter(prefix="/v1/customers/ai", tags=["AI 客户跟进"])


@router.post("/parse")
async def parse_customer_follow_up(
    request: CustomerAIParseRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team)
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
                user_message=context_message,
                team_id=team_id
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


# ==================== ReAct Agent 接口（已迁移到 LangGraph） ====================

from pydantic import BaseModel

# 注意：ai_tool_service 已删除，ReAct 接口已迁移到 web_assistant.py
# 使用 POST /v1/assistant/chat 和 /v1/assistant/workflow/continue 替代


class ReactContinueRequest(BaseModel):
    """继续 ReAct 循环请求（已废弃）"""
    session_id: str
    user_response: str


# 此接口已废弃，请使用 /v1/assistant/workflow/continue
# @router.post("/react/continue")  # 已移除


@router.get("/react/session/{session_id}")
async def get_react_session_status(
    session_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    获取 ReAct 会话状态

    Returns:
        - session_id
        - round_num
        - execution_history
        - status
    """
    session = ai_tool_service._load_react_session(session_id)

    if not session:
        return {"status": "expired", "message": "会话已过期"}

    return {
        "status": "active",
        "session_id": session_id,
        "round_num": session.get("round_num", 0),
        "execution_history": session.get("execution_history", []),
        "entity_context": session.get("entity_context")
    }

# ==================== 新增功能：AI 创建客户 ====================

@router.post("/create/parse")
async def parse_customer_create_info(
    request: CustomerAICreateParseRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team)
):
    """
    AI 解析客户创建信息（SSE 流式响应）
    
    用于 AI 智能创建客户
    """
    parser = EntityAIParserFactory.get_parser("customer")
    if not parser:
        raise HTTPException(status_code=500, detail="Parser not found")
    
    async def generate_sse():
        db = SessionLocal()
        try:
            async for event in parser.parse_stream(db, request.content, team_id):
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


@router.post("/create/submit", status_code=status.HTTP_201_CREATED)
async def create_customer_from_ai(
    request: CustomerAICreateRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    """
    从 AI 解析结果创建客户（用户确认后提交）
    
    创建客户 + 主联系人 + 触发档案生成 + 创建跟进记录
    """
    parser = EntityAIParserFactory.get_parser("customer")
    if not parser:
        raise HTTPException(status_code=500, detail="Parser not found")
    
    try:
        # 创建客户 + 主联系人
        customer = await parser.create_entity(
            db=db,
            parsed_data={
                "customer_info": request.customer_info.model_dump(),
                "contact_info": request.contact_info.model_dump(),
                "follow_up_info": request.follow_up_info.model_dump() if request.follow_up_info else None
            },
            user_id=str(current_user.id),
            team_id=team_id
        )
        
        # 执行创建后的额外操作（触发档案生成 + 创建跟进记录）
        await parser.post_create_actions(
            db=db,
            entity=customer,
            parsed_data={
                "customer_info": request.customer_info.model_dump(),
                "contact_info": request.contact_info.model_dump(),
                "follow_up_info": request.follow_up_info.model_dump() if request.follow_up_info else None
            },
            user_id=str(current_user.id),
            team_id=team_id
        )
        
        return {
            "id": customer.id,
            "account_name": customer.account_name,
            "city": customer.city,
            "status": customer.status,
            "profile_status": customer.profile_status
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败：{str(e)}")
