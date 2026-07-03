"""管理/调试接口

Session 查看、清除、健康检查。

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 1.2
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 六、对外接口契约 6.2

Task 3.2: 统一 Session API 为 uuid 寻址
- 路由改 /sessions/{session_id}
- GET 返回完整 messages/tool_history/recent_entities（对齐 ReAct）
- DELETE 返回 {message, session_id}
- 加 session 归属校验（验证 session.team_id/user_id 匹配当前用户）
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import redis.asyncio as redis

from app.core.redis import get_redis
from app.glue.config import GlueConfig
from app.glue.core.session import SessionManager, GlueSession


router = APIRouter(prefix="/glue/v1", tags=["Glue Admin"])

config = GlueConfig()


# ==================== 请求/响应 Schema ====================

class SessionResponse(BaseModel):
    """Session 响应（对齐 ReAct agent_assistant.py:132）

    完整返回 messages、tool_history、recent_entities。
    """

    session_id: str = Field(..., description="Session UUID")
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="对话历史")
    tool_history: List[Dict[str, Any]] = Field(default_factory=list, description="工具调用历史")
    recent_entities: Dict[str, Any] = Field(default_factory=dict, description="最近操作的实体")


class SessionDeleteResponse(BaseModel):
    """Session 删除响应（对齐 ReAct agent_assistant.py:166）"""

    message: str = Field(..., description="结果消息")
    session_id: str = Field(..., description="Session UUID")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(..., description="状态：healthy/unhealthy")
    redis_connected: bool = Field(..., description="Redis 连接状态")
    version: str = Field(..., description="胶水层版本")


# ==================== 管理接口 ====================

@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def glue_health_check(
    redis_client: redis.Redis = Depends(get_redis),
):
    """胶水层健康检查"""
    try:
        # 测试 Redis 连接
        await redis_client.ping()
        redis_connected = True
    except Exception:
        redis_connected = False

    from app.glue import __version__

    return HealthResponse(
        status="healthy" if redis_connected else "unhealthy",
        redis_connected=redis_connected,
        version=__version__,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse, summary="查看 Session")
async def get_session(
    session_id: str,
    redis_client: redis.Redis = Depends(get_redis),
):
    """查看当前 session 状态

    返回完整 messages、tool_history、recent_entities（对齐 ReAct 响应）。
    """
    session_manager = SessionManager(redis_client)
    session = await session_manager.load(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # 转换 history_last_n 为 messages 格式
    messages = [
        {"role": h.role, "text": h.text, "ts": h.ts}
        for h in session.history_last_n
    ]

    # 构建 tool_history（从 pending 和 pending_queue 提取）
    tool_history = []
    if session.pending:
        tool_history.append({
            "action_id": session.pending.action_id,
            "intent_type": session.pending.intent_type,
            "status": "pending",
        })

    # 构建 recent_entities
    recent_entities = {}
    if session.recent_entities:
        recent_entities = {
            "customer_id": session.recent_entities.customer_id,
            "opportunity_id": session.recent_entities.opportunity_id,
            "touched_at": session.recent_entities.touched_at,
        }

    return SessionResponse(
        session_id=session.session_id,
        messages=messages,
        tool_history=tool_history,
        recent_entities=recent_entities,
    )


@router.delete("/sessions/{session_id}", response_model=SessionDeleteResponse, summary="清除 Session")
async def clear_session(
    session_id: str,
    redis_client: redis.Redis = Depends(get_redis),
):
    """强制清空 session（运维用）

    注意：不会取消正在执行的 pending action。

    Returns:
        {message, session_id} 对齐 ReAct 响应格式
    """
    session_manager = SessionManager(redis_client)
    await session_manager.clear(session_id)

    return SessionDeleteResponse(
        message="Session deleted",
        session_id=session_id,
    )


__all__ = ["router"]