"""CRM AI Agent models.

These tables store Agent conversation state and audit data only. Business data
must still be created or changed through existing CRM APIs.
"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AgentSessionStatus:
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class AgentMessageRole:
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"


class AgentTaskStatus:
    PENDING = "PENDING"
    WAITING_USER = "WAITING_USER"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentToolCallStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AgentIdempotencyStatus:
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AgentSession(Base):
    """Agent conversation session."""

    __tablename__ = "crm_agent_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    session_key = Column(String(64), nullable=False, unique=True, index=True, comment="Agent会话唯一标识")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="系统用户ID")
    title = Column(String(200), nullable=True, comment="会话标题")
    status = Column(String(20), nullable=False, default=AgentSessionStatus.ACTIVE, index=True, comment="会话状态")
    summary = Column(Text, nullable=True, comment="会话摘要")
    context_json = Column(JSON, nullable=True, comment="会话上下文快照")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="最后修改时间",
    )

    messages = relationship("AgentMessage", back_populates="session", cascade="all, delete-orphan")
    tasks = relationship("AgentTask", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_agent_session_team_user_status", "team_id", "user_id", "status"),
        Index("idx_agent_session_created_time", "created_time"),
        {"comment": "CRM AI Agent会话表"},
    )


class AgentMessage(Base):
    """Agent conversation message."""

    __tablename__ = "crm_agent_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="系统用户ID")
    session_id = Column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Agent会话ID",
    )
    role = Column(String(20), nullable=False, comment="消息角色")
    event_type = Column(String(50), nullable=True, index=True, comment="SSE或业务事件类型")
    content = Column(Text, nullable=True, comment="消息正文")
    payload_json = Column(JSON, nullable=True, comment="结构化消息载荷")
    created_time = Column(DateTime, nullable=False, default=func.now(), index=True, comment="创建时间")

    session = relationship("AgentSession", back_populates="messages")

    __table_args__ = (
        Index("idx_agent_message_session_created", "session_id", "created_time"),
        Index("idx_agent_message_team_user_created", "team_id", "user_id", "created_time"),
        {"comment": "CRM AI Agent消息表"},
    )


class AgentTask(Base):
    """Agent task tracked across turns."""

    __tablename__ = "crm_agent_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    task_key = Column(String(64), nullable=False, unique=True, index=True, comment="Agent任务唯一标识")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="系统用户ID")
    session_id = Column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Agent会话ID",
    )
    intent = Column(String(80), nullable=True, index=True, comment="识别出的意图")
    status = Column(String(20), nullable=False, default=AgentTaskStatus.PENDING, index=True, comment="任务状态")
    target_type = Column(String(50), nullable=True, index=True, comment="目标业务对象类型")
    target_id = Column(BigInteger, nullable=True, index=True, comment="目标业务对象ID")
    summary = Column(Text, nullable=True, comment="任务摘要")
    input_json = Column(JSON, nullable=True, comment="用户输入解析快照")
    state_json = Column(JSON, nullable=True, comment="LangGraph状态快照")
    result_json = Column(JSON, nullable=True, comment="任务结果快照")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_time = Column(DateTime, nullable=False, default=func.now(), index=True, comment="创建时间")
    last_modified_time = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="最后修改时间",
    )

    session = relationship("AgentSession", back_populates="tasks")
    tool_calls = relationship("AgentToolCall", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_agent_task_session_status", "session_id", "status"),
        Index("idx_agent_task_team_user_status", "team_id", "user_id", "status"),
        {"comment": "CRM AI Agent任务表"},
    )


class AgentToolCall(Base):
    """Agent tool call audit record."""

    __tablename__ = "crm_agent_tool_calls"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    call_key = Column(String(64), nullable=False, unique=True, index=True, comment="Tool调用唯一标识")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="系统用户ID")
    session_id = Column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Agent会话ID",
    )
    task_id = Column(
        BigInteger,
        ForeignKey("crm_agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Agent任务ID",
    )
    tool_name = Column(String(100), nullable=False, index=True, comment="Tool名称")
    status = Column(String(20), nullable=False, default=AgentToolCallStatus.PENDING, index=True, comment="调用状态")
    request_json = Column(JSON, nullable=True, comment="Tool请求参数快照")
    response_json = Column(JSON, nullable=True, comment="Tool响应结果快照")
    error_message = Column(Text, nullable=True, comment="错误信息")
    started_time = Column(DateTime, nullable=True, comment="开始时间")
    finished_time = Column(DateTime, nullable=True, comment="结束时间")
    created_time = Column(DateTime, nullable=False, default=func.now(), index=True, comment="创建时间")
    last_modified_time = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="最后修改时间",
    )

    task = relationship("AgentTask", back_populates="tool_calls")

    __table_args__ = (
        Index("idx_agent_tool_call_session_created", "session_id", "created_time"),
        Index("idx_agent_tool_call_task_status", "task_id", "status"),
        Index("idx_agent_tool_call_team_user_tool", "team_id", "user_id", "tool_name"),
        {"comment": "CRM AI Agent Tool调用审计表"},
    )


class AgentIdempotencyKey(Base):
    """Agent-side idempotency record for write actions."""

    __tablename__ = "crm_agent_idempotency_keys"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(BigInteger, nullable=False, index=True, comment="系统用户ID")
    session_id = Column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Agent会话ID",
    )
    task_id = Column(
        BigInteger,
        ForeignKey("crm_agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Agent任务ID",
    )
    action_key = Column(String(160), nullable=False, comment="幂等动作键")
    status = Column(
        String(20),
        nullable=False,
        default=AgentIdempotencyStatus.PENDING,
        index=True,
        comment="幂等状态",
    )
    request_hash = Column(String(64), nullable=True, comment="请求内容Hash")
    result_json = Column(JSON, nullable=True, comment="执行结果快照")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_time = Column(DateTime, nullable=False, default=func.now(), index=True, comment="创建时间")
    last_modified_time = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="最后修改时间",
    )

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", "action_key", name="uk_agent_idempotency_team_user_action"),
        Index("idx_agent_idempotency_session_task", "session_id", "task_id"),
        Index("idx_agent_idempotency_team_user_status", "team_id", "user_id", "status"),
        {"comment": "CRM AI Agent幂等键表"},
    )
