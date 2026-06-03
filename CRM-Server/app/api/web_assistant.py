"""
Web AI 助手接口

用于 MagicWand 魔术棒功能，SSE 流式响应
"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user, get_db, get_current_user_team
from app.models.user import User
from app.schemas.web_assistant import WebAssistantRequest
from app.services.ai_skill_main import ai_skill_main_service


router = APIRouter(prefix="/api/v1/assistant", tags=["Web AI 助手"])


@router.post("/chat")
async def chat_with_assistant(
    request: WebAssistantRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    AI 助手聊天接口（SSE 流式响应）

    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 解析完成，返回结构化信息（等待用户确认）
    - result: 执行结果
    - error: 错误信息
    """
    async def generate_sse():
        db = SessionLocal()
        try:
            async for event in ai_skill_main_service.handle_message_stream_for_user(
                db=db,
                user=current_user,
                content=request.content,
                confirmed_skill=request.skill,
                confirmed_action=request.action,
                confirmed_params=request.params,
                team_id=team_id
            ):
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