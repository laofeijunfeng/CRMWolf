from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class CustomerIdentityTermStatus:
    ACTIVE = "ACTIVE"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class CustomerIdentityTermType:
    FULL_NAME = "full_name"
    NORMALIZED_NAME = "normalized_name"
    GENERATED_SHORT_NAME = "generated_short_name"
    ALIAS = "alias"
    HISTORICAL_MENTION = "historical_mention"
    DOMAIN = "domain"


class CustomerIdentityTermSource:
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    HUMAN = "human"
    FACT = "fact"
    HISTORICAL = "historical"


class CustomerIdentityTerm(Base):
    """Searchable customer identity term used by CRM Agent resolution."""

    __tablename__ = "crm_customer_identity_terms"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    tenant_id = Column(BigInteger, nullable=False, index=True, comment="租户ID，当前与团队ID一致")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户ID",
    )
    term = Column(String(255), nullable=False, comment="客户称呼、简称或匹配词")
    normalized_term = Column(String(255), nullable=False, comment="归一化匹配词")
    term_type = Column(String(50), nullable=False, index=True, comment="匹配词类型")
    source = Column(String(50), nullable=False, index=True, comment="来源")
    confidence = Column(Float, nullable=False, default=0.0, comment="置信度")
    status = Column(String(20), nullable=False, default=CustomerIdentityTermStatus.ACTIVE, index=True, comment="状态")
    conflict_group = Column(String(64), nullable=True, index=True, comment="冲突组")
    evidence = Column(Text, nullable=True, comment="生成或确认依据")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("team_id", "customer_id", "normalized_term", "term_type", name="uq_customer_identity_term"),
        Index("idx_customer_identity_term_lookup", "team_id", "normalized_term", "status"),
        Index("idx_customer_identity_term_customer", "team_id", "customer_id", "status"),
        {"comment": "客户身份解析匹配词表"},
    )
