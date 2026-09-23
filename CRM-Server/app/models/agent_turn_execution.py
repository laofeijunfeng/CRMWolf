"""Durable execution ledger for accepted CRM Agent turns."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class AgentTurnExecutionStatus:
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMMITTED = "PARTIALLY_COMMITTED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    FAILED = "FAILED"


class AgentTurnExecution(Base):
    """Frozen request and lease-fenced execution state for one client request."""

    __tablename__ = "crm_agent_turn_executions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("ate"),
        comment="执行记录对外ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Agent会话ID",
    )
    turn_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="Agent轮次ID")
    client_request_id: Mapped[str] = mapped_column(String(36), nullable=False, comment="客户端请求UUID")
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, comment="规范化输入SHA-256")
    request_input_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, comment="冻结的类型化输入")
    root_input_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, comment="冻结的Root输入")
    permission_codes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, comment="受理时权限代码快照")
    channel_context_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, comment="可信渠道上下文")
    selected_entity_ref_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True, comment="受理时服务端解析的实体引用"
    )
    message_display: Mapped[str] = mapped_column(String(20), nullable=False, comment="用户消息展示类型")
    entity_action_claim_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="实体动作消费ID")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="执行状态")
    lease_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="租约栅栏版本")
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="当前租约持有者")
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="当前租约到期时间")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="执行尝试次数")
    result_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="权威助手结果消息ID",
    )
    committed_resources_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list, comment="已确认提交的业务资源"
    )
    completed_command_ids_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="已确认完成的业务命令ID"
    )
    failed_command_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="失败的业务命令ID")
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="最近错误代码")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, comment="最后修改时间"
    )

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", "client_request_id", name="uq_agent_turn_execution_owner_request"),
        Index("idx_agent_turn_execution_session_request", "session_id", "client_request_id"),
        Index("idx_agent_turn_execution_recovery", "status", "lease_expires_at", "id"),
        {"comment": "CRM Agent持久执行与请求恢复账本"},
    )
