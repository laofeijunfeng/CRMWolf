"""Durable tombstones for deleted customer activities.

Customer activities are hard-deleted from the operational table.  The tombstone
keeps the deletion observable to the customer-profile read model so a failed
post-commit enqueue can still be discovered by watermark reconciliation.
"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class CustomerActivityDeletionTombstone(Base):
    __tablename__ = "crm_customer_activity_deletion_tombstones"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="删除水位主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        comment="客户ID",
    )
    activity_id = Column(BigInteger, nullable=False, comment="已删除客户活动ID")
    deal_journey_id = Column(BigInteger, nullable=True, comment="活动所属业务旅程ID快照")
    activity_occurred_at = Column(DateTime, nullable=True, comment="活动发生时间快照")
    activity_revision = Column(Integer, nullable=True, comment="删除前活动语义修订号")
    deleted_at = Column(DateTime, nullable=False, default=business_now, comment="删除时间")
    deleted_by = Column(String(100), nullable=True, comment="删除人系统用户ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("team_id", "activity_id", name="uq_customer_activity_deletion_tombstone"),
        Index("idx_customer_activity_deletion_customer", "team_id", "customer_id", "id"),
        Index("idx_customer_activity_deletion_time", "team_id", "customer_id", "deleted_at"),
        {"comment": "客户活动删除水位墓碑"},
    )
