"""Weekly suppression records for assistant open follow-up disposition cards."""

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, UniqueConstraint, text

from app.core.database import Base
from app.utils.time import business_now


class AssistantOpenFollowUpSuppression(Base):
    """Suppress one customer's open-follow-up card for a tenant-local week."""

    __tablename__ = "crm_assistant_open_follow_up_suppressions"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", name="fk_assistant_open_follow_up_suppressions_customer", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户ID",
    )
    week_start = Column(Date, nullable=False, comment="Asia/Shanghai 周一")
    created_time = Column(
        DateTime,
        nullable=False,
        default=business_now,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_time = Column(
        DateTime,
        nullable=False,
        default=business_now,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=business_now,
        comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "customer_id",
            "week_start",
            name="uq_assistant_open_follow_up_suppression_week",
        ),
        {"comment": "销售助手历史跟进任务按客户自然周抑制"},
    )
