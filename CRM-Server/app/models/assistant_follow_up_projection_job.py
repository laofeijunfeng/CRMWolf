"""Durable Assistant 2.0 follow-up projection jobs."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class AssistantFollowUpProjectionJobStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    EXHAUSTED = "EXHAUSTED"
    TERMINAL = frozenset({COMPLETED, SKIPPED, EXHAUSTED})


class AssistantFollowUpProjectionJob(Base):
    """One committed Assistant 2.0 activity projection attempt."""

    __tablename__ = "crm_assistant_follow_up_projection_jobs"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(String(64), nullable=False, default=lambda: generate_public_id("afpj"), comment="对外任务ID")
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    activity_id = Column(
        BigInteger,
        ForeignKey("crm_customer_activities.id", name="fk_assistant_follow_up_projection_jobs_activity"),
        nullable=False,
        comment="客户活动ID",
    )
    activity_revision = Column(Integer, nullable=False, comment="活动修订号")
    trigger_type = Column(String(80), nullable=False, comment="投影触发类型")
    actor_id = Column(String(100), nullable=True, comment="触发用户ID")
    status = Column(
        String(20),
        nullable=False,
        default=AssistantFollowUpProjectionJobStatus.QUEUED,
        server_default=AssistantFollowUpProjectionJobStatus.QUEUED,
        comment="持久任务状态",
    )
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0", comment="执行尝试次数")
    next_attempt_at = Column(DateTime, nullable=True, comment="下次重试时间")
    lease_token = Column(String(64), nullable=True, comment="执行租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, comment="租约过期时间")
    result_json = Column(JSON, nullable=True, comment="投影结果")
    error_message = Column(Text, nullable=True, comment="最近错误")
    created_time = Column(
        DateTime,
        nullable=False,
        default=business_now,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_time = Column(
        DateTime,
        nullable=False,
        default=business_now,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=business_now,
        comment="更新时间",
    )
    started_at = Column(DateTime, nullable=True, comment="首次开始时间")
    finished_at = Column(DateTime, nullable=True, comment="完成时间")

    __table_args__ = (
        UniqueConstraint("public_id", name="uq_assistant_follow_up_projection_jobs_public_id"),
        UniqueConstraint(
            "team_id",
            "activity_id",
            "activity_revision",
            "trigger_type",
            name="uq_assistant_follow_up_projection_job_identity",
        ),
        Index("idx_assistant_follow_up_projection_jobs_team", "team_id", "activity_id"),
        Index(
            "idx_assistant_follow_up_projection_jobs_status",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
        Index("idx_assistant_follow_up_projection_jobs_lease", "lease_token"),
        {"comment": "Assistant 2.0 客户活动跟进任务投影持久任务表"},
    )
