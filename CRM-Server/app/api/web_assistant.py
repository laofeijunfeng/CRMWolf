"""
Web AI 助手接口

用于 MagicWand 魔术棒功能，SSE 流式响应
使用 Function Calling 方案
"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User
from app.schemas.web_assistant import WebAssistantRequest
from app.services.ai_tool_service import ai_tool_service


router = APIRouter(prefix="/v1/assistant", tags=["Web AI 助手"])


@router.post("/chat")
async def chat_with_assistant(
    request: WebAssistantRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    AI 助手聊天接口（SSE 流式响应）

    使用 Function Calling 解析用户意图并执行操作

    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 解析完成，返回工具和参数（等待用户确认）
    - result: 执行结果
    - error: 错误信息
    """
    async def generate_sse():
        db = SessionLocal()
        try:
            # 判断是否是确认执行
            if request.tool and request.params:
                # 用户已确认，直接执行
                async for event in ai_tool_service.execute_confirmed_tool(
                    db, current_user, request.tool, request.params, team_id
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            else:
                # 需要解析
                async for event in ai_tool_service.handle_message_stream(
                    db, current_user.id, current_user, request.content, team_id
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