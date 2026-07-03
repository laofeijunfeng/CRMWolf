"""Inbound 接口

接收各渠道的用户输入，处理对话流程。

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 1.1
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 六、对外接口契约

Task 3.2: 统一 Session API 为 uuid 寻址
- session_id 改为 uuid 寻址
- 首次请求不带 session_id 时自动创建
- 返回 session_id 用于后续请求关联
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
import redis.asyncio as redis
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis
from app.glue.config import GlueConfig, SessionMode
from app.glue.core.session import SessionManager, GlueSession
from app.glue.core.user_mapper import UserMappingService
from app.glue.core.dedup import DedupManager
from app.glue.core.dialogue import DialogueEngine, DialogueAction


router = APIRouter(prefix="/glue/v1", tags=["Glue Inbound"])

config = GlueConfig()


# ==================== 请求/响应 Schema ====================

class InboundRequest(BaseModel):
    """Inbound 请求"""

    channel_user_id: str = Field(..., description="渠道用户 ID（open_id/userid）")
    channel_chat_id: Optional[str] = Field(None, description="单聊/群 ID")
    message_id: str = Field(..., description="消息唯一标识（去重用）")
    text: str = Field(..., description="用户输入文本")
    timestamp: int = Field(..., description="消息时间戳")

    # Session 寻址（Task 3.2: uuid 寻址）
    session_id: Optional[str] = Field(None, description="Session UUID（后续请求必带）")

    # 网页直连时直接带身份
    crm_user_id_override: Optional[int] = Field(None, description="CRM 用户 ID（网页渠道）")
    session_token: Optional[str] = Field(None, description="JWT session token（网页渠道）")


class InboundResponse(BaseModel):
    """Inbound 响应"""

    ok: bool = Field(..., description="是否成功")
    delivery: str = Field(..., description="交付方式：async/sync")
    session_id: str = Field(..., description="Session UUID（用于后续请求）")
    reply_token: Optional[str] = Field(None, description="回复 token（异步）")
    reply: Optional[dict] = Field(None, description="同步回复内容")


# ==================== Inbound 接口 ====================

@router.post("/inbound", response_model=InboundResponse, summary="接收用户输入")
async def inbound(
    request: InboundRequest,
    x_glue_channel: str = Header(..., description="渠道类型"),
    x_glue_signature: Optional[str] = Header(None, description="验签"),
    db: Session = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """接收各渠道的用户输入

    流程:
    1. 验签（按渠道）
    2. message_id 去重
    3. 解析 crm_user_id + tenant_id
    4. 推队列（IM 异步）或直接处理（web 同步）
    5. 返回 reply_token 或 reply

    Args:
        request: 请求参数
        x_glue_channel: 渠道类型（feishu/wecom/web/test）
        x_glue_signature: 签名（可选）

    Returns:
        InboundResponse: 异步返回 reply_token，同步返回 reply
    """
    # 1. 渠道校验
    if x_glue_channel not in config.SUPPORTED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"不支持渠道: {x_glue_channel}")

    # 2. 消息去重
    dedup = DedupManager(redis_client)
    if not await dedup.check(request.message_id):
        # 重复消息，跳过（无 session_id）
        return InboundResponse(ok=True, delivery="skipped", session_id="", reply_token=None)

    # 3. 解析 crm_user_id + tenant_id
    user_mapper = UserMappingService(db)

    if request.crm_user_id_override:
        # 网页直连：使用 override
        crm_user_id = request.crm_user_id_override
        # TODO: tenant_id 应从用户信息获取
        tenant_id = 1
    else:
        # IM 渠道：解析映射
        crm_user_id, tenant_id = await user_mapper.resolve_with_tenant(
            x_glue_channel, request.channel_user_id
        )

        if crm_user_id is None:
            # 未绑定账号（无 session_id）
            return InboundResponse(
                ok=False,
                delivery="sync",
                session_id="",
                reply={
                    "text": "请先绑定账号后再使用 AI 助手。",
                    "mode": "error",
                },
            )

    # 4. 加载或创建 session（Task 3.2: uuid 寻址）
    session_manager = SessionManager(redis_client)

    if request.session_id:
        # 后续请求：加载已有 session
        session = await session_manager.load(request.session_id)
        if session is None:
            # session 不存在或已过期，创建新的
            session_id = await session_manager.create(str(tenant_id), crm_user_id)
            session = await session_manager.load(session_id)
        else:
            # 校验 session 归属（安全检查）
            if session.tenant_id != str(tenant_id) or session.crm_user_id != crm_user_id:
                raise HTTPException(status_code=403, detail="Session 归属不匹配")
    else:
        # 首次请求：创建新 session
        session_id = await session_manager.create(str(tenant_id), crm_user_id)
        session = await session_manager.load(session_id)

    # 5. 添加历史
    await session_manager.add_history(session, "user", request.text)

    # 6. 判断交付方式
    channel_config = config.CHANNEL_CONFIG.get(x_glue_channel, {})
    async_delivery = channel_config.get("async_delivery", True)

    # 获取认证 token（用于调用 AI 端点）
    auth_token = request.session_token

    if async_delivery:
        # IM 异步队列尚未实现，诚实返回 503
        raise HTTPException(
            status_code=503,
            detail="IM 异步投递队列尚未实现，请使用 web 同步渠道或联系管理员",
        )
    else:
        # 网页同步：对话引擎处理
        # 每次请求创建新的 DialogueEngine（注入 db, tenant_id, user_id）
        engine = DialogueEngine(db, tenant_id, crm_user_id)

        # 执行对话流程
        result = await engine.dispatch(session, request.text, auth_token)

        # 更新 session mode
        if result.next_mode:
            session.mode = result.next_mode
            await session_manager.save(session)

        reply_text = result.message
        reply_mode = session.mode

        # 处理执行结果
        if result.action == DialogueAction.EXECUTE_ACTION and result.success:
            # TODO: 调用 ActionExecutor 执行实际操作
            # 清除 pending，回到 IDLE
            session.pending = None
            session.mode = SessionMode.IDLE
            await session_manager.save(session)
            reply_mode = SessionMode.IDLE

        elif result.action == DialogueAction.CANCEL_ACTION:
            # 取消操作，清除 pending
            session.pending = None
            session.mode = SessionMode.IDLE
            await session_manager.save(session)
            reply_mode = SessionMode.IDLE

        # 添加回复历史
        if result.needs_response:
            await session_manager.add_history(session, "assistant", reply_text)

        return InboundResponse(
            ok=True,
            delivery="sync",
            session_id=session.session_id,
            reply={
                "text": reply_text,
                "mode": reply_mode,
                "data": result.data,
            },
        )


__all__ = ["router"]