"""
聊天消息接收接口（通用）
"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.database import SessionLocal
from app.schemas.chat_message import ChatMessageRequest
from app.services.ai_skill_main import ai_skill_main_service

router = APIRouter(prefix="/api/v1/chat", tags=["聊天机器人"])


@router.post("/receive")
async def receive_chat_message(
    request: ChatMessageRequest
):
    """
    接收聊天消息（SSE 流式响应）

    支持：飞书、钉钉、企业微信、Slack 等平台

    SSE 事件类型：
    - status: 状态更新
    - content: AI 响应内容片段
    - result: 最终结果
    - error: 错误信息
    """
    async def generate_sse():
        """生成 SSE 流式响应（在内部管理数据库 session）"""
        db = SessionLocal()
        try:
            async for event in ai_skill_main_service.handle_message_stream(
                db=db,
                channel_user_id=request.channel_user_id,
                channel_type=request.channel_type,
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