"""Durable registries for the unified CRM Agent runtime."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # SQLAlchemy resolves mapped annotations at runtime.
from typing import TypeAlias

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


class AgentQueryResultSet(Base):
    """Immutable query continuation context; business rows are never copied here."""

    __tablename__ = "crm_agent_query_result_sets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("rs"),
        comment="服务端签发的结果集ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Agent会话ID",
    )
    source_message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_messages.id", ondelete="CASCADE"),
        nullable=False,
        comment="生成该结果集的助手消息ID",
    )
    parent_result_set_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_query_result_sets.id", ondelete="SET NULL"),
        nullable=True,
        comment="分页或细化查询的父结果集",
    )
    resource: Mapped[str] = mapped_column(String(50), nullable=False, comment="Query Catalog资源")
    query_json: Mapped[JSONObject] = mapped_column(JSON, nullable=False, comment="Canonical CRMQuerySpec")
    ordered_entity_refs_json: Mapped[list[JSONObject]] = mapped_column(
        JSON, nullable=False, comment="当前页有序实体引用"
    )
    page_json: Mapped[JSONObject] = mapped_column(JSON, nullable=False, comment="Opaque分页上下文")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="当前页实体数量")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="结果集失效时间")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        Index(
            "idx_agent_query_result_set_owner_expiry",
            "team_id",
            "user_id",
            "session_id",
            "expires_at",
        ),
        Index("idx_agent_query_result_set_source_message", "source_message_id"),
        Index("idx_agent_query_result_set_parent", "parent_result_set_id"),
        {"comment": "CRM Agent不可变查询结果集注册表"},
    )


class AgentUIActionStatus:
    ACTIVE = "ACTIVE"
    CONSUMING = "CONSUMING"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class AgentUIActionConsumptionMode:
    REUSABLE = "REUSABLE"
    ONE_SHOT = "ONE_SHOT"


class AgentUIActionRootContextRole:
    """How an action participates in Root turn context resolution."""

    RESUMABLE_WORKFLOW = "RESUMABLE_WORKFLOW"
    PENDING_CASE = "PENDING_CASE"
    PROJECTION_ONLY = "PROJECTION_ONLY"


class AgentUIAction(Base):
    """Server-owned action target and one-shot consumption ledger."""

    __tablename__ = "crm_agent_ui_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("act"),
        comment="服务端签发的Action ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Agent会话ID",
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_messages.id", ondelete="CASCADE"),
        nullable=False,
        comment="Action所属消息ID",
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False, comment="Agent UI Action类型")
    root_context_role: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        comment="Root上下文角色: 可恢复Workflow、待确认事项或仅展示投影",
    )
    target_json: Mapped[JSONObject] = mapped_column(JSON, nullable=False, comment="服务端签发的不可变Action目标")
    consumption_mode: Mapped[str] = mapped_column(String(20), nullable=False, comment="REUSABLE或ONE_SHOT")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AgentUIActionStatus.ACTIVE,
        comment="Action状态",
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="Action失效时间")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="消费完成时间")
    submitted_values: Mapped[JSONObject | None] = mapped_column(
        JSON,
        nullable=True,
        comment="一次性交互最终提交值(只读展示快照)",
    )
    consumed_request_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="消费请求client_request_id",
    )
    result_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_agent_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="幂等重放的结果消息ID",
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="乐观锁版本")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=business_now,
        comment="最后修改时间",
    )

    __table_args__ = (
        Index(
            "idx_agent_ui_action_owner_status_expiry",
            "team_id",
            "user_id",
            "session_id",
            "status",
            "expires_at",
        ),
        Index("idx_agent_ui_action_message", "message_id"),
        Index("idx_agent_ui_action_consumed_request", "consumed_request_id"),
        {"comment": "CRM Agent UI Action注册与消费表"},
    )
