"""管理/调试接口

Session 查看、清除、健康检查。

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 1.2
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 六、对外接口契约 6.2
"""

from typing import Dict, Any, Optional
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
    """Session 响应（脱敏）"""

    v: int = Field(..., description="版本号")
    tenant_id: str = Field(..., description="租户 ID")
    crm_user_id: int = Field(..., description="CRM 用户 ID")
    mode: str = Field(..., description="会话状态")
    updated_at: int = Field(..., description="更新时间")

    has_pending: bool = Field(False, description="是否有 pending action")
    pending_expired: Optional[bool] = Field(None, description="pending 是否过期")

    recent_customer_id: Optional[int] = Field(None, description="最近客户 ID")
    recent_opportunity_id: Optional[int] = Field(None, description="最近商机 ID")

    history_count: int = Field(0, description="历史记录数量")


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


@router.get("/sessions/{tenant_id}/{crm_user_id}", response_model=SessionResponse, summary="查看 Session")
async def get_session(
    tenant_id: str,
    crm_user_id: int,
    redis_client: redis.Redis = Depends(get_redis),
):
    """查看当前 session 状态（脱敏）

    不返回完整的 pending 内容，仅返回状态信息。
    """
    session_manager = SessionManager(redis_client)
    session = await session_manager.load(tenant_id, crm_user_id)

    # 判断 pending 是否过期
    pending_expired = None
    if session.pending:
        pending_expired = session.pending.is_expired()

    return SessionResponse(
        v=session.v,
        tenant_id=session.tenant_id,
        crm_user_id=session.crm_user_id,
        mode=session.mode,
        updated_at=session.updated_at,
        has_pending=session.pending is not None,
        pending_expired=pending_expired,
        recent_customer_id=session.recent_entities.customer_id if session.recent_entities else None,
        recent_opportunity_id=session.recent_entities.opportunity_id if session.recent_entities else None,
        history_count=len(session.history_last_n),
    )


@router.delete("/sessions/{tenant_id}/{crm_user_id}", summary="清除 Session")
async def clear_session(
    tenant_id: str,
    crm_user_id: int,
    redis_client: redis.Redis = Depends(get_redis),
):
    """强制清空 session（运维用）

    注意：不会取消正在执行的 pending action。
    """
    session_manager = SessionManager(redis_client)
    await session_manager.clear(tenant_id, crm_user_id)

    return {"ok": True, "message": "Session cleared"}


__all__ = ["router"]