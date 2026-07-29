"""IM channel models for Agent conversations."""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class IMBotProvider:
    FEISHU = "feishu"


class IMBotStatus:
    ENABLED = "enabled"
    DISABLED = "disabled"


class IMInboundEventStatus:
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class AgentChannelSession(Base):
    """Mapping from an external IM conversation to a CRM Agent session."""

    __tablename__ = "agent_channel_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="系统用户ID")
    provider = Column(String(30), nullable=False, index=True, comment="IM渠道")
    external_tenant_key = Column(String(128), nullable=True, comment="外部租户标识")
    chat_id = Column(String(128), nullable=False, comment="外部会话ID")
    thread_id = Column(String(128), nullable=False, default="", comment="外部话题/线程ID")
    agent_session_id = Column(BigInteger, ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    last_message_id = Column(String(128), nullable=True, comment="最近处理的外部消息ID")
    status = Column(String(20), nullable=False, default="active", index=True, comment="状态")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "team_id",
            "user_id",
            "chat_id",
            "thread_id",
            name="uq_agent_channel_session_scope",
        ),
        Index("idx_agent_channel_session_lookup", "provider", "team_id", "chat_id", "user_id"),
        {"comment": "Agent IM渠道会话映射表"},
    )


class IMInboundEvent(Base):
    """Inbound IM event idempotency and audit record."""

    __tablename__ = "im_inbound_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    provider = Column(String(30), nullable=False, index=True, comment="IM渠道")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID")
    event_id = Column(String(128), nullable=False, comment="渠道事件ID")
    message_id = Column(String(128), nullable=True, index=True, comment="渠道消息ID")
    status = Column(String(20), nullable=False, default=IMInboundEventStatus.RECEIVED, index=True, comment="处理状态")
    request_hash = Column(String(64), nullable=True, comment="请求Hash")
    response_message_id = Column(String(128), nullable=True, comment="回复消息ID")
    agent_session_id = Column(BigInteger, nullable=True, index=True, comment="回复绑定的Agent会话ID")
    agent_task_id = Column(BigInteger, nullable=True, index=True, comment="回复绑定的Agent任务ID")
    agent_interaction_type = Column(String(80), nullable=True, comment="回复绑定的Agent交互事件类型")
    error_message = Column(Text, nullable=True, comment="错误信息")
    raw_event = Column(JSON, nullable=True, comment="必要事件快照")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    processed_time = Column(DateTime, nullable=True, comment="处理时间")

    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_im_inbound_provider_event"),
        Index("idx_im_inbound_team_status", "team_id", "status"),
        {"comment": "IM入站事件幂等表"},
    )
