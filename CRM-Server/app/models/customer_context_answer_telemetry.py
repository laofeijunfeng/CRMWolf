from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, Index, Integer, String, Text

from app.core.database import Base
from app.utils.time import business_now


class CustomerContextAnswerTelemetry(Base):
    """Persistent quality telemetry for customer context answers."""

    __tablename__ = "crm_customer_context_answer_telemetry"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    tenant_id = Column(BigInteger, nullable=False, index=True, comment="租户ID，当前与团队ID一致")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, nullable=True, index=True, comment="客户ID")
    question_text = Column(Text, nullable=True, comment="用户问题")
    answer_source = Column(String(80), nullable=False, index=True, comment="回答来源")
    answer_mode = Column(String(30), nullable=False, index=True, comment="回答模式")
    model = Column(String(120), nullable=True, index=True, comment="模型")
    fallback_reason = Column(String(120), nullable=True, index=True, comment="降级原因")
    fallback_error = Column(Text, nullable=True, comment="降级错误")
    retrieval_status = Column(String(40), nullable=True, index=True, comment="检索状态")
    retrieval_strategy = Column(String(80), nullable=True, index=True, comment="检索策略")
    semantic_evidence_count = Column(Integer, nullable=False, default=0, comment="语义证据数量")
    citation_count = Column(Integer, nullable=False, default=0, comment="引用数量")
    top_score = Column(Float, nullable=True, comment="最高召回分")
    min_score = Column(Float, nullable=True, comment="最低接纳分")
    raw_count = Column(Integer, nullable=True, comment="原始召回数量")
    returned_count = Column(Integer, nullable=True, comment="返回证据数量")
    dropped_count = Column(Integer, nullable=True, comment="被阈值过滤数量")
    used_sections_json = Column(JSON, nullable=True, comment="回答使用的上下文分区")
    missing_context_json = Column(JSON, nullable=True, comment="缺失上下文")
    citations_json = Column(JSON, nullable=True, comment="回答引用")
    retrieval_json = Column(JSON, nullable=True, comment="检索状态快照")
    created_time = Column(DateTime, nullable=False, default=business_now, index=True, comment="创建时间")

    __table_args__ = (
        Index("idx_customer_context_answer_customer_time", "team_id", "customer_id", "created_time"),
        Index("idx_customer_context_answer_quality", "team_id", "answer_mode", "retrieval_status"),
        {"comment": "客户上下文回答质量遥测表"},
    )
