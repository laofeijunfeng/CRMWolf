"""Durable projection ledger for PendingTask native interrupts."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class AgentPendingInterruptProjectionStatus:
    PENDING = "PENDING"
    PROJECTING = "PROJECTING"
    PROJECTED = "PROJECTED"
    FAILED = "FAILED"


class AgentPendingInterruptDeliveryStatus:
    PENDING = "PENDING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    INLINE_VISIBLE = "INLINE_VISIBLE"
    SKIPPED = "SKIPPED"

    TERMINAL = frozenset({DELIVERED, INLINE_VISIBLE, SKIPPED})


class AgentPendingInterruptProjection(Base):
    """Lease-guarded business projection and event-delivery outbox record."""

    __tablename__ = "crm_agent_pending_interrupt_projections"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="用户ID")
    session_id = Column(BigInteger, nullable=False, index=True, comment="Agent会话ID")
    task_id = Column(BigInteger, nullable=True, index=True, comment="待处理Agent任务ID")
    projection_key = Column(String(255), nullable=False, comment="中断投影幂等键")
    continuation_json = Column(JSON, nullable=False, comment="PendingTask精确continuation")
    interrupt_json = Column(JSON, nullable=False, comment="原生interrupt载荷")
    status = Column(
        String(20),
        nullable=False,
        default=AgentPendingInterruptProjectionStatus.PENDING,
        index=True,
        comment="业务投影状态",
    )
    attempt_count = Column(Integer, nullable=False, default=0, comment="业务投影尝试次数")
    lease_token = Column(String(64), nullable=True, index=True, comment="业务投影租约")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="业务投影租约过期时间")
    result_json = Column(JSON, nullable=True, comment="权威投影结果及稳定事件")
    error_message = Column(Text, nullable=True, comment="业务投影最近错误")
    delivery_status = Column(
        String(20),
        nullable=False,
        default=AgentPendingInterruptDeliveryStatus.PENDING,
        index=True,
        comment="事件投递状态",
    )
    delivery_attempt_count = Column(Integer, nullable=False, default=0, comment="事件投递尝试次数")
    delivery_lease_token = Column(String(64), nullable=True, index=True, comment="事件投递租约")
    delivery_lease_expires_at = Column(DateTime, nullable=True, index=True, comment="事件投递租约过期时间")
    delivery_reason_code = Column(String(80), nullable=True, comment="事件投递结果原因码")
    delivery_error_message = Column(Text, nullable=True, comment="事件投递最近错误")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(
        DateTime,
        nullable=False,
        default=business_now,
        onupdate=business_now,
        comment="更新时间",
    )
    projected_at = Column(DateTime, nullable=True, comment="业务投影完成时间")
    delivered_at = Column(DateTime, nullable=True, comment="事件投递完成时间")

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "user_id",
            "projection_key",
            name="uq_agent_pending_interrupt_projection_key",
        ),
        Index(
            "idx_agent_pending_interrupt_projection_recovery",
            "status",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        Index(
            "idx_agent_pending_interrupt_delivery_recovery",
            "delivery_status",
            "delivery_lease_expires_at",
            "delivery_attempt_count",
            "created_time",
        ),
        Index(
            "idx_agent_pending_interrupt_owner",
            "team_id",
            "user_id",
            "session_id",
            "created_time",
        ),
        {"comment": "Agent PendingTask原生中断持久投影与事件投递表"},
    )
