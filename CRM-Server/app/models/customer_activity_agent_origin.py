"""Immutable Agent-origin attribution for customer activities."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class CustomerActivityAgentOrigin(Base):
    """Record which Agent turn originally created one customer activity.

    This relation deliberately belongs to the activity rather than a post-commit
    revision. Revisions protect background execution; the origin remains stable
    when AI subsequently enriches the same activity.
    """

    __tablename__ = "crm_customer_activity_agent_origins"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    activity_id = Column(
        BigInteger,
        ForeignKey("crm_customer_activities.id", ondelete="CASCADE"),
        nullable=False,
        comment="客户活动ID",
    )
    owner_id = Column(String(100), nullable=False, index=True, comment="Agent归属用户ID")
    agent_session_id = Column(BigInteger, nullable=False, index=True, comment="来源Agent会话ID")
    source_user_message_id = Column(BigInteger, nullable=True, index=True, comment="来源用户消息ID")
    source_assistant_message_id = Column(BigInteger, nullable=False, index=True, comment="来源助手消息ID")
    agent_operation_public_id = Column(String(64), nullable=False, index=True, comment="来源Agent异步操作ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("team_id", "activity_id", name="uq_customer_activity_agent_origin"),
        Index("idx_customer_activity_agent_origin_session", "team_id", "owner_id", "agent_session_id"),
        Index("idx_customer_activity_agent_origin_assistant", "team_id", "source_assistant_message_id"),
        {"comment": "客户活动Agent来源归属表"},
    )
