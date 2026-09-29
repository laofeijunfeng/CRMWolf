"""Durable task state for the Agent 2.0 sales assistant."""

# ruff: noqa: RUF001

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class AssistantTaskStatus:
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class AssistantWaitingType:
    """Closed enum of pause points; extending requires a design review."""

    FIELD = "FIELD"
    CONFIRMATION = "CONFIRMATION"
    ACTIVITY_KIND = "ACTIVITY_KIND"
    OBJECT_SELECTION = "OBJECT_SELECTION"


class AssistantTask(Base):
    """Single source of truth for one sales-assistant task.

    Mutations must go through the transition function in
    ``app.services.assistant.task_state``; nothing else writes this table.
    """

    __tablename__ = "crm_assistant_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("ast"),
        comment="任务对外ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="任务状态")
    # Frozen business intent once first accepted; never rewritten afterwards.
    goal: Mapped[str] = mapped_column(Text, nullable=False, comment="任务目标")
    activity_kind: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="活动类型")
    # Field-level draft: accepted fields, candidate fields, current gaps.
    draft_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, comment="字段级草稿")
    # Append-only observation list is stored in crm_assistant_actions.
    waiting_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="当前等待类型")
    waiting_field: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="等待中的字段名")
    waiting_json: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, comment="等待点完整载荷（question_id/prompt）"
    )
    # Server-authoritative zone: bound object ids, confirmation receipts.
    authority_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, comment="权威区")
    committed_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list, comment="已提交结果（只增不减）"
    )
    budget_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已消耗步数")
    budget_max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=50, comment="步数上限")
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="最近错误代码")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="乐观锁版本")
    active_turn_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="正在处理的持久轮次ID")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, comment="最后修改时间"
    )

    __table_args__ = (
        Index("idx_assistant_task_owner_active", "team_id", "user_id", "status"),
        {"comment": "销售助手任务状态表（Agent 2.0 单一事实来源）"},
    )


class AssistantAction(Base):
    """Append-only action log; every state-changing step lands here exactly once."""

    __tablename__ = "crm_assistant_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("asa"),
        comment="动作对外ID",
    )
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="助手任务ID")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")
    actor: Mapped[str] = mapped_column(String(20), nullable=False, comment="触发者：MODEL/USER/SYSTEM")
    action: Mapped[str] = mapped_column(String(64), nullable=False, comment="动作名")
    input_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, comment="输入摘要")
    result_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, comment="结果")
    event_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="会话事件类型")
    event_key: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="会话事件幂等键")
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="关联界面元素ID")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        Index("idx_assistant_action_task", "task_id", "id"),
        Index("uq_assistant_action_event", "team_id", "task_id", "event_key", unique=True),
        {"comment": "销售助手动作日志（只追加）"},
    )
