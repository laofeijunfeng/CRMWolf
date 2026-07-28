from sqlalchemy import Column, BigInteger, String, Text, DateTime, Index, ForeignKey, func

from app.core.database import Base


class DealJourneyStatus:
    ACTIVE = "ACTIVE"
    WON = "WON"
    LOST = "LOST"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class DealJourneyEventType:
    OPPORTUNITY_CREATED = "opportunity_created"
    OPPORTUNITY_STAGE_CHANGED = "opportunity_stage_changed"
    OPPORTUNITY_WON = "opportunity_won"
    OPPORTUNITY_LOST = "opportunity_lost"
    CONTRACT_CREATED = "contract_created"
    CONTRACT_SIGNED = "contract_signed"
    PAYMENT_PLAN_CREATED = "payment_plan_created"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_CONFIRMED = "payment_confirmed"
    INVOICE_APPLIED = "invoice_applied"
    INVOICE_ISSUED = "invoice_issued"
    FOLLOW_UP_ADDED = "follow_up_added"


class DealJourneySourceType:
    OPPORTUNITY = "opportunity"
    OPPORTUNITY_STAGE_SNAPSHOT = "opportunity_stage_snapshot"
    CONTRACT = "contract"
    PAYMENT_PLAN = "payment_plan"
    PAYMENT_RECORD = "payment_record"
    INVOICE_APPLICATION = "invoice_application"
    CUSTOMER_FOLLOW_UP = "customer_follow_up"


class CustomerDealJourney(Base):
    __tablename__ = "crm_customer_deal_journeys"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False, comment="客户ID")
    primary_opportunity_id = Column(BigInteger, ForeignKey("crm_opportunities.id", ondelete="SET NULL"), nullable=True, comment="主商机ID")
    name = Column(String(255), nullable=False, comment="成交旅程名称")
    status = Column(String(20), nullable=False, default=DealJourneyStatus.ACTIVE, comment="成交旅程状态")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    closed_at = Column(DateTime, nullable=True, comment="结束时间")
    last_event_at = Column(DateTime, nullable=True, comment="最近事件时间")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_deal_journey_team_customer", "team_id", "customer_id"),
        Index("idx_deal_journey_primary_opportunity", "primary_opportunity_id", unique=True),
        Index("idx_deal_journey_status", "status"),
        Index("idx_deal_journey_last_event_at", "last_event_at"),
        {"comment": "客户成交旅程表"},
    )


class CustomerDealJourneyEvent(Base):
    __tablename__ = "crm_customer_deal_journey_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    deal_journey_id = Column(BigInteger, ForeignKey("crm_customer_deal_journeys.id", ondelete="CASCADE"), nullable=False, comment="成交旅程ID")
    customer_id = Column(BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False, comment="客户ID")
    event_type = Column(String(50), nullable=False, comment="事件类型")
    event_time = Column(DateTime, nullable=False, comment="事件发生时间")
    source_type = Column(String(50), nullable=False, comment="来源对象类型")
    source_id = Column(BigInteger, nullable=True, comment="来源对象ID")
    actor_id = Column(String(100), nullable=True, comment="操作者系统用户ID")
    summary = Column(Text, nullable=True, comment="事件摘要")
    metadata_json = Column(Text, nullable=True, comment="事件元数据JSON")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_deal_journey_event_journey_time", "deal_journey_id", "event_time"),
        Index("idx_deal_journey_event_customer_time", "team_id", "customer_id", "event_time"),
        Index("idx_deal_journey_event_source", "source_type", "source_id"),
        Index("idx_deal_journey_event_type", "event_type"),
        {"comment": "客户成交旅程事件表"},
    )
