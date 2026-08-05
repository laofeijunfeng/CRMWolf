from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class CustomerVectorDocumentSourceType:
    CUSTOMER = "customer"
    CUSTOMER_PROFILE = "customer_profile"
    CUSTOMER_BRIEF = "customer_brief"
    FOLLOW_UP = "follow_up"
    BUSINESS_FLOW = "business_flow"
    OPPORTUNITY = "opportunity"
    CONTRACT = "contract"
    PAYMENT = "payment"
    CONTACT = "contact"
    AGENT_JUDGEMENT = "agent_judgement"


class CustomerVectorDocumentSyncStatus:
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    DELETE_PENDING = "DELETE_PENDING"
    DELETED = "DELETED"


class CustomerVectorDocument(Base):
    """Business-owned metadata for customer evidence stored in the vector index."""

    __tablename__ = "crm_customer_vector_documents"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    document_key = Column(String(64), nullable=False, unique=True, index=True, comment="证据文档幂等键")
    tenant_id = Column(BigInteger, nullable=False, index=True, comment="租户ID, 当前与团队ID一致")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户ID",
    )
    source_type = Column(String(50), nullable=False, index=True, comment="来源类型")
    source_object_id = Column(String(100), nullable=False, comment="来源对象ID")
    business_object_type = Column(String(50), nullable=True, index=True, comment="业务对象类型")
    business_object_id = Column(String(100), nullable=True, comment="业务对象ID")
    title = Column(String(255), nullable=False, comment="证据标题")
    text = Column(Text, nullable=False, comment="可检索证据文本")
    text_hash = Column(String(64), nullable=False, index=True, comment="证据文本SHA256")
    qdrant_point_id = Column(String(64), nullable=False, unique=True, comment="Qdrant point ID")
    occurred_at = Column(DateTime, nullable=True, index=True, comment="业务发生时间")
    confidence = Column(Float, nullable=True, comment="证据置信度")
    visibility_scope = Column(String(30), nullable=False, default="team", comment="可见范围")
    metadata_version = Column(BigInteger, nullable=False, default=1, comment="元数据版本")
    sync_status = Column(
        String(20),
        nullable=False,
        default=CustomerVectorDocumentSyncStatus.PENDING,
        index=True,
        comment="向量同步状态",
    )
    sync_error = Column(Text, nullable=True, comment="向量同步失败原因")
    synced_at = Column(DateTime, nullable=True, comment="向量同步时间")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("team_id", "source_type", "source_object_id", name="uq_customer_vector_source"),
        Index("idx_customer_vector_customer_status", "customer_id", "sync_status"),
        Index("idx_customer_vector_team_customer_time", "team_id", "customer_id", "occurred_at"),
        {"comment": "客户智能档案向量证据元数据表"},
    )
