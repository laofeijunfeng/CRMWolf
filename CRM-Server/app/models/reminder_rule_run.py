from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class ReminderRuleRun(Base):
    """One successful reminder for one object inside one silence window."""

    __tablename__ = "crm_reminder_rule_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    rule_id = Column(BigInteger, nullable=False, comment="提醒规则ID")
    object_type = Column(String(40), nullable=False, comment="业务对象")
    object_id = Column(BigInteger, nullable=False, comment="业务对象ID")
    window_key = Column(String(120), nullable=False, comment="同一静默窗口去重键")
    recipient_ids = Column(Text, nullable=False, comment="接收用户ID")
    message = Column(Text, nullable=False, comment="实际发送文案")
    sent_count = Column(Integer, nullable=False, default=0, comment="送达人数")
    skipped_count = Column(Integer, nullable=False, default=0, comment="跳过人数")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="发送时间")

    __table_args__ = (
        UniqueConstraint("rule_id", "object_id", "window_key", name="uq_reminder_rule_run_window"),
        Index("idx_crm_reminder_rule_runs_team", "team_id", "created_time"),
        {"comment": "提醒规则运行记录"},
    )
