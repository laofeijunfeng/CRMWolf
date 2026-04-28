"""
AI 助手接口（内置 Web 端）
"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user
from app.models.user import User
from app.schemas.ai_assistant import AIAssistantChatRequest
from app.services.ai_skill_main import ai_skill_main_service
from app.crud.conversation_log import conversation_log_crud


router = APIRouter(prefix="/api/v1/ai", tags=["AI 助手"])


@router.get("/history")
async def get_chat_history(
    limit: int = 20,
    current_user: User = Depends(get_current_active_user)
):
    """
    获取 AI 助手历史记录

    返回用户的最近会话日志（按时间倒序）
    """
    db = SessionLocal()
    try:
        logs = conversation_log_crud.get_logs_by_user(db, current_user.id, limit)

        # 按时间正序排列（旧消息在前）
        logs.reverse()

        history = [
            {
                "id": log.id,
                "request_text": log.request_text,
                "execution_result": log.execution_result,
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
            if log.channel_type == "web_assistant"  # 只返回 AI 助手的记录
        ]

        return {
            "code": 0,
            "message": "success",
            "data": history
        }
    finally:
        db.close()


@router.post("/chat")
async def chat_with_assistant(
    request: AIAssistantChatRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    内置 AI 助手聊天（SSE 流式响应）

    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 意图解析完成
    - result: 最终结果
    - error: 错误信息

    使用 JWT 认证，适用于 Web 端用户
    """
    async def generate_sse():
        """生成 SSE 流式响应（在内部管理数据库 session）"""
        db = SessionLocal()
        try:
            async for event in ai_skill_main_service.handle_message_stream_for_user(
                db=db,
                user=current_user,
                content=request.content
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