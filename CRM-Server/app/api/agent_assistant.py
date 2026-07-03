"""
Agent AI 助手接口（Glue 代理）

Phase 3.5: /v1/agent/chat 代理到 Glue DialogueEngine
- 保持端点路径不变（前端兼容）
- 内部使用 GlueSSEStreamer
- Session 端点代理到 Glue admin

核心设计：
- Glue DialogueEngine + SSE 流式响应
- uuid session_id 寻址
- 事件契约对齐 ReAct（start/result/complete/error）

遵循规范：
- team_id 必传（get_current_user_team）
- Pydantic 强制校验
"""

import json
import logging
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.deps import get_current_active_user, get_current_user_team
from app.core.redis import get_redis_client
from app.models.user import User

# ===== Glue 组件（替代 ReAct）=====
from app.glue.core.dialogue import DialogueEngine
from app.glue.core.sse_streamer import GlueSSEStreamer
from app.glue.core.session import SessionManager, GlueSession

logger = logging.getLogger(__name__)


# ==================== Router ====================

router = APIRouter(prefix="/v1/agent", tags=["Agent AI 助手（Glue 代理）"])


# ==================== Request Models ====================


class AgentAssistantRequest(BaseModel):
    """Agent 助手请求"""
    content: str = Field(description="用户消息内容")
    session_id: Optional[str] = Field(default=None, description="Session ID（可选，自动生成）")


class SessionStateRequest(BaseModel):
    """Session 状态查询请求"""
    session_id: str = Field(description="Session ID")


# ==================== Main Chat Endpoint ====================


@router.post("/chat")
async def chat_with_agent(
    request: AgentAssistantRequest,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
):
    """
    Agent 助手聊天接口（SSE 流式响应）—— Glue 代理

    Phase 3.5: 代理到 Glue DialogueEngine + GlueSSEStreamer。
    端点路径保持不变（前端兼容），内部走 Glue。

    SSE 事件类型（对齐 ReAct，前端依赖）：
    - start: Session 启动
    - result: 最终结果
    - complete: 完成标记
    - error: 错误信息

    中间事件（Glue 语义）：
    - intent: 意图识别
    - entity: 实体消解
    - preview: 预览快照
    - execute: 执行结果
    """
    # 生成或使用现有 session_id
    session_id = request.session_id or str(uuid4())

    # Glue 组件初始化
    redis_client = get_redis_client()
    session_manager = SessionManager(redis_client)
    engine = DialogueEngine(redis_client=redis_client, team_id=team_id, user_id=current_user.id)
    streamer = GlueSSEStreamer()

    # 加载或创建 session
    session = await session_manager.load(session_id)
    if session is None:
        # 创建新 session
        session = GlueSession(
            session_id=session_id,
            tenant_id=str(team_id),
            crm_user_id=current_user.id,  # int 类型
            history_last_n=[],  # dataclass 字段名
            pending=None,
        )

    async def generate_sse():
        """SSE 流式生成"""
        try:
            # 使用 Glue SSE Streamer
            async for event in streamer.stream(
                engine=engine,
                session=session,
                session_id=session_id,
                text=request.content,
            ):
                yield event

            # 保存 session（更新 history）
            await session_manager.save(session)

        except Exception as e:
            logger.error(f"Glue agent execution error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== Session State Endpoint（代理到 Glue admin）====================


@router.get("/session/{session_id}")
async def get_session_state(
    session_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取 Session 状态（代理到 Glue SessionManager）

    Args:
        session_id: Session ID（uuid）

    Returns:
        Session 状态信息
    """
    redis_client = get_redis_client()
    session_manager = SessionManager(redis_client)

    session = await session_manager.load(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # 权限校验：session 必须属于当前用户的 team
    if session.tenant_id != str(team_id):
        raise HTTPException(status_code=403, detail="Session belongs to different team")
    if session.crm_user_id != current_user.id:  # int 类型比较
        raise HTTPException(status_code=403, detail="Session belongs to different user")

    # 返回格式对齐 ReAct（前端兼容）
    return {
        "session_id": session_id,
        "messages": [
            {"role": h.role, "content": h.content}
            for h in (session.history_last_n or [])[-50:]  # list 属性，取最近50条
        ],
        "tool_history": [],  # Glue 无 tool_history（用 phase history 替代）
        "recent_entities": [],  # Glue 用 session.pending 替代
        "pending": session.pending,
    }


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
):
    """
    删除 Session（代理到 Glue SessionManager）

    Args:
        session_id: Session ID（uuid）

    Returns:
        删除结果
    """
    redis_client = get_redis_client()
    session_manager = SessionManager(redis_client)

    # 先校验权限
    session = await session_manager.load(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.tenant_id != str(team_id):
        raise HTTPException(status_code=403, detail="Session belongs to different team")
    if session.crm_user_id != current_user.id:  # int 类型比较
        raise HTTPException(status_code=403, detail="Session belongs to different user")

    # 删除
    await session_manager.clear(session_id)

    return {"message": "Session deleted", "session_id": session_id}


__all__ = ["router"]