"""Durable user-facing projections for asynchronous Agent work."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.utils.time import business_now


class AgentAsyncOperationStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentAsyncOperation(Base):
    """Stable projection of background work shown independently from chat SSE."""

    __tablename__ = "crm_agent_async_operations"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(String(64), nullable=False, unique=True, index=True, comment="对外操作ID")
    operation_key = Column(String(200), nullable=False, unique=True, index=True, comment="操作幂等键")
    request_id = Column(String(120), nullable=False, index=True, comment="后台请求ID")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="用户ID")
    session_id = Column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="来源 Agent 会话ID",
    )
    source_user_message_id = Column(BigInteger, nullable=True, index=True, comment="来源用户消息ID")
    source_assistant_message_id = Column(BigInteger, nullable=True, index=True, comment="来源助手消息ID")
    operation_type = Column(String(80), nullable=False, index=True, comment="异步操作类型")
    resource_type = Column(String(50), nullable=False, index=True, comment="业务资源类型")
    resource_id = Column(BigInteger, nullable=True, index=True, comment="内部业务资源ID")
    resource_public_id = Column(String(80), nullable=True, index=True, comment="对外业务资源ID")
    status = Column(String(30), nullable=False, default=AgentAsyncOperationStatus.QUEUED, index=True, comment="状态")
    summary = Column(Text, nullable=True, comment="用户可见摘要")
    current_step = Column(String(120), nullable=True, comment="当前步骤")
    graph_thread_id = Column(String(240), nullable=True, index=True, comment="LangGraph thread ID")
    result_json = Column(JSON, nullable=True, comment="可回放结果摘要")
    error_message = Column(Text, nullable=True, comment="错误信息")
    started_time = Column(DateTime, nullable=True, index=True, comment="开始时间")
    finished_time = Column(DateTime, nullable=True, index=True, comment="结束时间")
    next_retry_at = Column(DateTime, nullable=True, index=True, comment="下次重试时间")
    attempt_count = Column(Integer, nullable=False, default=0, comment="已开始执行次数")
    next_event_sequence = Column(Integer, nullable=False, default=1, comment="下一个事件序号")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    events = relationship(
        "AgentAsyncOperationEvent",
        back_populates="operation",
        cascade="all, delete-orphan",
        order_by="AgentAsyncOperationEvent.sequence",
    )

    __table_args__ = (
        UniqueConstraint("operation_key", name="uq_agent_async_operation_key"),
        Index("idx_agent_async_operation_owner_session", "team_id", "user_id", "session_id", "created_time"),
        Index("idx_agent_async_operation_owner_status", "team_id", "user_id", "status", "updated_time"),
        Index("idx_agent_async_operation_resource", "team_id", "resource_type", "resource_id"),
        {"comment": "Agent 异步操作用户可见投影表"},
    )


class AgentAsyncOperationEvent(Base):
    """Append-only lifecycle event for an Agent async operation."""

    __tablename__ = "crm_agent_async_operation_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    operation_id = Column(
        BigInteger,
        ForeignKey("crm_agent_async_operations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="异步操作ID",
    )
    event_key = Column(String(200), nullable=False, comment="操作内事件幂等键")
    sequence = Column(Integer, nullable=False, comment="操作内递增序号")
    event_type = Column(String(30), nullable=False, index=True, comment="事件类型")
    status = Column(String(30), nullable=False, index=True, comment="事件后的操作状态")
    step = Column(String(120), nullable=True, comment="步骤标识")
    message = Column(Text, nullable=True, comment="用户可见进度说明")
    payload_json = Column(JSON, nullable=True, comment="结构化事件载荷")
    occurred_at = Column(DateTime, nullable=False, default=business_now, index=True, comment="业务发生时间")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")

    operation = relationship("AgentAsyncOperation", back_populates="events")

    __table_args__ = (
        UniqueConstraint("operation_id", "event_key", name="uq_agent_async_operation_event_key"),
        UniqueConstraint("operation_id", "sequence", name="uq_agent_async_operation_event_sequence"),
        Index("idx_agent_async_operation_event_replay", "operation_id", "sequence"),
        {"comment": "Agent 异步操作追加事件表"},
    )
