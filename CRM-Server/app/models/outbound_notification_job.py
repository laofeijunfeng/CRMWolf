"""Durable outbox for outbound Feishu / approval notifications."""

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class OutboundNotificationEventType:
    APPROVAL_PENDING = "approval_pending"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_CANCELLED = "approval_cancelled"
    APPROVAL_ISSUED = "approval_issued"
    APPROVAL_REMINDER = "approval_reminder"
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_STATUS_WON = "account_status_won"
    ACCOUNT_STATUS_LOST = "account_status_lost"
    CUSTOMER_RETURNED = "customer_returned"
    LEAD_CLAIMED = "lead_claimed"
    LEAD_ASSIGNED = "lead_assigned"
    OPPORTUNITY_WON = "opportunity_won"
    OPPORTUNITY_LOST = "opportunity_lost"

    APPROVAL = frozenset(
        {
            APPROVAL_PENDING,
            APPROVAL_APPROVED,
            APPROVAL_REJECTED,
            APPROVAL_CANCELLED,
            APPROVAL_ISSUED,
            APPROVAL_REMINDER,
        }
    )
    BUSINESS = frozenset(
        {
            ACCOUNT_CREATED,
            ACCOUNT_STATUS_WON,
            ACCOUNT_STATUS_LOST,
            CUSTOMER_RETURNED,
            LEAD_CLAIMED,
            LEAD_ASSIGNED,
            OPPORTUNITY_WON,
            OPPORTUNITY_LOST,
        }
    )
    ALL = APPROVAL | BUSINESS


class OutboundNotificationJobStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    EXHAUSTED = "EXHAUSTED"

    TERMINAL = frozenset({COMPLETED, SKIPPED, EXHAUSTED})


class OutboundNotificationJob(Base):
    """Business source of truth for one outbound notification attempt chain."""

    __tablename__ = "crm_outbound_notification_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("onj"),
        comment="对外任务ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    event_type = Column(String(40), nullable=False, index=True, comment="通知事件类型")
    idempotency_key = Column(String(160), nullable=False, comment="幂等键")
    approval_id = Column(BigInteger, nullable=True, index=True, comment="审批实例ID")
    node_id = Column(BigInteger, nullable=True, comment="目标审批节点ID")
    business_type = Column(String(40), nullable=False, comment="业务类型")
    business_id = Column(BigInteger, nullable=False, comment="业务单据ID")
    actor_id = Column(String(100), nullable=True, comment="触发用户ID")
    recipient_user_ids = Column(JSON, nullable=False, comment="接收人用户ID列表")
    payload_json = Column(JSON, nullable=True, comment="通知意图附加数据")
    status = Column(
        String(20),
        nullable=False,
        default=OutboundNotificationJobStatus.QUEUED,
        index=True,
        comment="执行状态",
    )
    attempt_count = Column(Integer, nullable=False, default=0, comment="执行次数")
    next_attempt_at = Column(DateTime, nullable=True, index=True, comment="下次恢复时间")
    lease_token = Column(String(64), nullable=True, index=True, comment="当前执行租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="当前执行租约过期时间")
    result_json = Column(JSON, nullable=True, comment="执行结果")
    error_message = Column(Text, nullable=True, comment="最近错误")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="首次开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('approval_pending', 'approval_approved', 'approval_rejected', "
            "'approval_cancelled', 'approval_issued', 'approval_reminder', "
            "'account_created', 'account_status_won', 'account_status_lost', "
            "'customer_returned', 'lead_claimed', 'lead_assigned', "
            "'opportunity_won', 'opportunity_lost')",
            name="ck_outbound_notification_job_event_type",
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'FAILED', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
            name="ck_outbound_notification_job_status",
        ),
        UniqueConstraint("team_id", "idempotency_key", name="uq_outbound_notification_job_idempotency"),
        Index(
            "idx_outbound_notification_job_recovery",
            "status",
            "next_attempt_at",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        {"comment": "出站通知持久任务表"},
    )
