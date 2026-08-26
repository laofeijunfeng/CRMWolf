from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class CustomerFactStatus:
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class CustomerFactRevisionType:
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    REACTIVATED = "REACTIVATED"


class CustomerFact(Base):
    """Structured customer intelligence fact derived from evidence."""

    __tablename__ = "crm_customer_facts"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    fact_key = Column(String(64), nullable=False, unique=True, index=True, comment="客户事实幂等键")
    tenant_id = Column(BigInteger, nullable=False, index=True, comment="租户ID，当前与团队ID一致")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户ID",
    )
    fact_type = Column(String(50), nullable=False, index=True, comment="事实类型")
    subject = Column(String(255), nullable=True, comment="事实主体")
    content = Column(Text, nullable=False, comment="事实内容")
    confidence = Column(Float, nullable=False, default=0.0, comment="事实置信度")
    status = Column(String(20), nullable=False, default=CustomerFactStatus.ACTIVE, index=True, comment="事实状态")
    version = Column(Integer, nullable=False, default=1, comment="事实版本号")
    occurred_at = Column(DateTime, nullable=True, index=True, comment="事实发生时间")
    extracted_at = Column(DateTime, nullable=False, default=business_now, comment="事实提取时间")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("team_id", "customer_id", "fact_type", "subject", name="uq_customer_fact_subject"),
        Index("idx_customer_fact_customer_status", "team_id", "customer_id", "status"),
        Index("idx_customer_fact_type_time", "team_id", "customer_id", "fact_type", "occurred_at"),
        {"comment": "客户智能事实表"},
    )


class CustomerFactSource(Base):
    """Evidence source binding for a customer fact."""

    __tablename__ = "crm_customer_fact_sources"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    fact_id = Column(
        BigInteger,
        ForeignKey("crm_customer_facts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户事实ID",
    )
    source_type = Column(String(50), nullable=False, index=True, comment="来源类型")
    source_object_id = Column(String(100), nullable=False, comment="来源对象ID")
    business_object_type = Column(String(50), nullable=True, index=True, comment="业务对象类型")
    business_object_id = Column(String(100), nullable=True, comment="业务对象ID")
    evidence_id = Column(String(64), nullable=True, index=True, comment="向量证据ID")
    quote = Column(Text, nullable=True, comment="引用片段")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("fact_id", "source_type", "source_object_id", name="uq_customer_fact_source"),
        Index("idx_customer_fact_source_business", "business_object_type", "business_object_id"),
        {"comment": "客户智能事实来源表"},
    )


class CustomerFactRevision(Base):
    """Versioned audit record for a customer fact."""

    __tablename__ = "crm_customer_fact_revisions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    fact_id = Column(
        BigInteger,
        ForeignKey("crm_customer_facts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户事实ID",
    )
    version = Column(Integer, nullable=False, comment="修订后的事实版本号")
    change_type = Column(String(20), nullable=False, index=True, comment="修订类型")
    previous_content = Column(Text, nullable=True, comment="修订前事实内容")
    new_content = Column(Text, nullable=False, comment="修订后事实内容")
    previous_confidence = Column(Float, nullable=True, comment="修订前置信度")
    new_confidence = Column(Float, nullable=False, comment="修订后置信度")
    previous_status = Column(String(20), nullable=True, comment="修订前状态")
    new_status = Column(String(20), nullable=False, comment="修订后状态")
    previous_occurred_at = Column(DateTime, nullable=True, comment="修订前发生时间")
    new_occurred_at = Column(DateTime, nullable=True, comment="修订后发生时间")
    source_type = Column(String(50), nullable=True, index=True, comment="触发本次修订的来源类型")
    source_object_id = Column(String(100), nullable=True, comment="触发本次修订的来源对象ID")
    business_object_type = Column(String(50), nullable=True, index=True, comment="业务对象类型")
    business_object_id = Column(String(100), nullable=True, comment="业务对象ID")
    evidence_id = Column(String(64), nullable=True, index=True, comment="向量证据ID")
    quote = Column(Text, nullable=True, comment="引用片段")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("fact_id", "version", name="uq_customer_fact_revision_version"),
        Index("idx_customer_fact_revision_source", "source_type", "source_object_id"),
        {"comment": "客户智能事实版本审计表"},
    )
