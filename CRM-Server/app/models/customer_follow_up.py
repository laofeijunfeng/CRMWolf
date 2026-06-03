from sqlalchemy import Column, BigInteger, String, DateTime, Text, Index, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class CustomerFollowUp(Base):
    __tablename__ = "crm_customer_follow_ups"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=True, comment="关联的客户ID")
    original_lead_id = Column(BigInteger, ForeignKey("crm_leads.id", ondelete="SET NULL"), nullable=True, comment="原始的线索ID")
    content = Column(Text, nullable=False, comment="跟进内容")
    method = Column(String(50), nullable=False, comment="跟进方式")
    next_follow_time = Column(DateTime, nullable=True, comment="计划下次跟进时间")
    next_action = Column(Text, nullable=True, comment="下一步动作内容")
    creator_id = Column(String(100), nullable=False, comment="记录创建人")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="记录创建时间")

    __table_args__ = (
        Index('idx_customer_id', 'customer_id'),
        Index('idx_original_lead_id', 'original_lead_id'),
        Index('idx_creator_id', 'creator_id'),
        Index('idx_next_follow_time', 'next_follow_time'),
        Index('idx_created_time', 'created_time'),
        Index('idx_team_id', 'team_id'),
        {'comment': '客户跟进记录表'}
    )
