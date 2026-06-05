"""
聊天消息接收接口（通用）
"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.database import SessionLocal
from app.schemas.chat_message import ChatMessageRequest
from app.services.ai_tool_service import ai_tool_service

router = APIRouter(prefix="/v1/chat", tags=["聊天机器人"])


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
    - parsed: 解析完成（等待确认）
    - result: 最终结果
    - error: 错误信息
    """
    async def generate_sse():
        """生成 SSE 流式响应"""
        db = SessionLocal()
        try:
            # 查找用户
            from app.crud.user import user_crud
            user = user_crud.get_by_channel_id(db, request.channel_user_id, request.channel_type)

            if not user:
                yield f"data: {json.dumps({'event': 'error', 'message': '用户未绑定，请先绑定账号'})}\n\n"
                return

            # 获取用户当前团队
            from app.crud.team import team_crud
            team_id = team_crud.get_user_current_team(db, user.id)
            if not team_id:
                yield f"data: {json.dumps({'event': 'error', 'message': '用户未加入任何团队'})}\n\n"
                return

            async for event in ai_tool_service.handle_message_stream(
                db=db,
                user_id=user.id,
                user=user,
                content=request.content,
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