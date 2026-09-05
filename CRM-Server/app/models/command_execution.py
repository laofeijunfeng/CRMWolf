"""Durable execution state for user initiated, non-Agent commands.

The table deliberately stores command metadata and a small JSON result summary,
not request bodies or file contents.  It gives the UI a stable operation id to
query when a network failure happens after the server may have committed.
"""

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Index, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class CommandExecutionStatus:
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    PARTIAL = "PARTIAL"

    TERMINAL = frozenset({SUCCEEDED, FAILED, UNKNOWN, CONFLICT, PARTIAL})


class CommandExecution(Base):
    __tablename__ = "crm_command_executions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    operation_id = Column(String(64), nullable=False, unique=True, index=True, comment="对外操作ID")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    actor_id = Column(String(100), nullable=False, comment="操作人ID")
    command_type = Column(String(80), nullable=False, comment="命令类型")
    resource_type = Column(String(40), nullable=True, comment="资源类型")
    resource_public_id = Column(String(128), nullable=True, comment="资源对外ID")
    idempotency_key = Column(String(128), nullable=True, comment="客户端幂等键")
    request_fingerprint = Column(String(64), nullable=True, comment="请求指纹")
    status = Column(String(20), nullable=False, default=CommandExecutionStatus.PENDING, index=True, comment="执行状态")
    result_json = Column(JSON, nullable=True, comment="脱敏结果摘要")
    error_code = Column(String(80), nullable=True, comment="稳定错误码")
    error_message = Column(Text, nullable=True, comment="面向用户的错误摘要")
    retryable = Column(Boolean, nullable=False, default=False, comment="是否允许重试")
    correlation_id = Column(String(128), nullable=True, comment="链路追踪ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")
    completed_time = Column(DateTime, nullable=True, comment="完成时间")

    __table_args__ = (
        UniqueConstraint("team_id", "idempotency_key", name="uq_command_execution_team_idempotency"),
        Index("idx_command_execution_team_status_created", "team_id", "status", "created_time"),
        Index("idx_command_execution_resource", "team_id", "resource_type", "resource_public_id"),
        {"comment": "非 Agent 用户命令执行记录"},
    )

    def __repr__(self) -> str:
        return f"<CommandExecution(operation_id={self.operation_id}, status={self.status})>"
