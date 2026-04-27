from sqlalchemy import Column, BigInteger, String, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class EventAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    CONVERT = "CONVERT"
    WIN = "WIN"
    LOSE = "LOSE"


class PrimaryResourceType(str, enum.Enum):
    LEAD = "LEAD"
    CUSTOMER = "CUSTOMER"
    OPPORTUNITY = "OPPORTUNITY"
    CONTRACT = "CONTRACT"
    INVOICE = "INVOICE"
    PAYMENT_PLAN = "PAYMENT_PLAN"
    PAYMENT_RECORD = "PAYMENT_RECORD"


class OperationLog(Base):
    __tablename__ = "crm_operation_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    
    event_id = Column(String(64), nullable=False, unique=True, comment="事件唯一ID")
    event_type = Column(String(50), nullable=False, comment="事件类型")
    event_action = Column(String(20), nullable=False, comment="事件动作")
    
    primary_resource_type = Column(String(20), nullable=False, comment="主资源类型")
    primary_resource_id = Column(BigInteger, nullable=False, comment="主资源ID")
    
    secondary_resource_type = Column(String(20), nullable=True, comment="次资源类型")
    secondary_resource_id = Column(BigInteger, nullable=True, comment="次资源ID")
    
    operator_id = Column(String(100), nullable=False, comment="操作人ID")
    operator_name = Column(String(100), nullable=True, comment="操作人姓名")
    
    operated_at = Column(DateTime, nullable=False, default=func.now(), comment="操作时间")
    
    content = Column(JSON, nullable=False, comment="事件内容")
    remark = Column(String(500), nullable=True, comment="备注")
    
    __table_args__ = (
        Index('idx_event_id', 'event_id'),
        Index('idx_primary_resource', 'primary_resource_type', 'primary_resource_id', 'operated_at'),
        Index('idx_event_type', 'event_type'),
        Index('idx_operator_id', 'operator_id'),
        Index('idx_operated_at', 'operated_at'),
        {'comment': '操作记录表'}
    )

    def __repr__(self):
        return f"<OperationLog(id={self.id}, event_type={self.event_type}, primary_resource_id={self.primary_resource_id})>"
