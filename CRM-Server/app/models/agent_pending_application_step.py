"""Durable ledger for hidden PendingTask application steps."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class AgentPendingApplicationStepStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentPendingApplicationStep(Base):
    __tablename__ = "crm_agent_pending_application_steps"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="用户ID")
    session_id = Column(BigInteger, nullable=False, index=True, comment="Agent会话ID")
    task_id = Column(BigInteger, nullable=True, index=True, comment="待处理Agent任务ID")
    step_id = Column(String(255), nullable=False, comment="稳定应用步骤幂等键")
    step_type = Column(String(64), nullable=False, index=True, comment="应用步骤类型")
    continuation_json = Column(JSON, nullable=False, comment="PendingTask精确continuation")
    request_json = Column(JSON, nullable=False, comment="checkpoint-safe步骤请求")
    status = Column(
        String(20),
        nullable=False,
        default=AgentPendingApplicationStepStatus.PENDING,
        index=True,
        comment="执行状态",
    )
    attempt_count = Column(Integer, nullable=False, default=0, comment="执行尝试次数")
    lease_token = Column(String(64), nullable=True, index=True, comment="执行租约")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="执行租约过期时间")
    result_json = Column(JSON, nullable=True, comment="稳定JSON执行结果")
    error_message = Column(Text, nullable=True, comment="最近错误")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(
        DateTime,
        nullable=False,
        default=business_now,
        onupdate=business_now,
        comment="更新时间",
    )
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", "step_id", name="uq_agent_pending_application_step_id"),
        Index(
            "idx_agent_pending_application_step_recovery",
            "status",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        Index(
            "idx_agent_pending_application_step_owner",
            "team_id",
            "user_id",
            "session_id",
            "created_time",
        ),
        {"comment": "Agent PendingTask内部应用步骤持久执行账本"},
    )
