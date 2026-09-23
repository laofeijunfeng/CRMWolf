from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, String, text

from app.core.database import Base
from app.models.workflow import WorkflowDslType
from app.utils.time import business_now


class ReminderRule(Base):
    """Team-level scheduled notification rule with versioned execution semantics."""

    __tablename__ = "crm_reminder_rules"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    name = Column(String(100), nullable=False, comment="规则名称")
    object_type = Column(String(40), nullable=False, comment="业务对象")
    trigger = Column(String(20), nullable=False, comment="schedule/change/date")
    rule = Column(WorkflowDslType, nullable=False, comment="提醒规则JSON")
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用")
    created_by = Column(Integer, nullable=True, comment="创建人用户ID")
    revision = Column(
        Integer, nullable=False, default=1, server_default="1", onupdate=text("revision + 1"), comment="乐观锁修订号"
    )
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    __table_args__ = (
        Index("idx_crm_reminder_rules_team", "team_id"),
        Index("idx_crm_reminder_rules_object", "team_id", "object_type"),
        {"comment": "团队提醒规则"},
    )
