from sqlalchemy import Column, BigInteger, String, DateTime, Text, JSON, Index, Boolean, Integer
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
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")

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

    # ==================== 撤销支持字段（新增） ====================
    undoable = Column(Boolean, default=False, comment="是否可撤销")
    undo_ttl = Column(Integer, default=10, comment="撤销窗口（秒）")
    undo_deadline = Column(DateTime, nullable=True, comment="撤销截止时间")
    undone = Column(Boolean, default=False, comment="是否已撤销")
    undo_by = Column(String(100), nullable=True, comment="撤销操作人ID")
    undo_at = Column(DateTime, nullable=True, comment="撤销时间")

    # ==================== Workflow 关联字段（新增） ====================
    workflow_session_id = Column(String(64), nullable=True, index=True, comment="Workflow Session ID")
    step_id = Column(String(32), nullable=True, comment="Workflow 步骤ID")
    parent_operation_id = Column(BigInteger, nullable=True, comment="父操作ID（用于级联撤销）")

    # ==================== 快照字段（新增） ====================
    before_snapshot = Column(JSON, nullable=True, comment="操作前状态快照")
    after_snapshot = Column(JSON, nullable=True, comment="操作后状态快照")

    __table_args__ = (
        Index('idx_event_id', 'event_id'),
        Index('idx_primary_resource', 'primary_resource_type', 'primary_resource_id', 'operated_at'),
        Index('idx_event_type', 'event_type'),
        Index('idx_operator_id', 'operator_id'),
        Index('idx_operated_at', 'operated_at'),
        Index('idx_operation_log_team_id', 'team_id'),
        Index('idx_workflow_session', 'workflow_session_id'),  # 新增索引
        Index('idx_undoable', 'undoable', 'undone', 'undo_deadline'),  # 新增索引
        {'comment': '操作记录表'}
    )

    def __repr__(self):
        return f"<OperationLog(id={self.id}, event_type={self.event_type}, primary_resource_id={self.primary_resource_id})>"
