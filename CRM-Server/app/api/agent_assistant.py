"""
Agent AI 助手接口
基于 ReAct 循环架构

核心设计：
- 使用 CRMWolfAgent（ReAct 循环）
- SSE 流式响应（复用 sse_wrapper）
- 支持会话恢复（session_id）

遵循规范：
- team_id 必传（get_current_user_team）
- Pydantic 强制校验
"""

import json
from uuid import uuid4
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User

from app.services.agent import CRMWolfAgent
from app.services.agent.sse_streamer import AgentSSEStreamer


# ==================== Router ====================

router = APIRouter(prefix="/v1/agent", tags=["Agent AI 助手"])


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
    Agent 助手聊天接口（SSE 流式响应）

    使用 CRMWolfAgent（ReAct 循环）执行 AI 助手流程。

    SSE 事件类型：
    - start: Session 启动
    - reasoning: Agent 推理过程
    - tool_call: 工具调用开始
    - tool_result: 工具执行结果
    - round_complete: ReAct 循环一轮完成
    - complete: Agent 完成
    - error: 错误信息
    """
    # 生成或使用现有 session_id
    session_id = request.session_id or str(uuid4())

    async def generate_sse():
        db = SessionLocal()
        try:
            # ===== 创建 Agent =====
            agent = CRMWolfAgent(db, team_id, current_user.id)

            # ===== 使用 SSE Streamer =====
            streamer = AgentSSEStreamer()

            # 流式输出 Agent 运行过程
            async for event in streamer.stream_agent_run(agent, request.content, session_id):
                yield event

        except Exception as e:
            import logging
            logging.error(f"Agent execution error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

        finally:
            db.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== Session State Endpoint ====================


@router.get("/session/{session_id}")
async def get_session_state(
    session_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取 Session 状态

    Args:
        session_id: Session ID

    Returns:
        Session 状态信息
    """
    from app.services.agent.memory import AgentMemory
    from app.services.langgraph.checkpointer import redis_client

    db = SessionLocal()
    try:
        memory = AgentMemory(db, team_id, current_user.id, redis_client)
        memory.load_session(session_id)

        return {
            "session_id": session_id,
            "messages": memory.messages,
            "tool_history": memory.tool_history,
            "recent_entities": memory.recent_entities,
        }

    finally:
        db.close()


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
):
    """
    删除 Session

    Args:
        session_id: Session ID

    Returns:
        删除结果
    """
    from app.services.langgraph.checkpointer import redis_client

    # 删除 Redis 中的 Session
    redis_client.delete(f"agent_session:{session_id}")

    return {"message": "Session deleted", "session_id": session_id}


__all__ = ["router"]