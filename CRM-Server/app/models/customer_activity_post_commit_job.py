"""Durable execution records for customer-activity post-commit workflows."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class CustomerActivityPostCommitJobStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    EXHAUSTED = "EXHAUSTED"

    TERMINAL = frozenset({COMPLETED, SKIPPED, EXHAUSTED})


class CustomerActivityPostCommitJob(Base):
    """Business source of truth for one revision-scoped post-commit run."""

    __tablename__ = "crm_customer_activity_post_commit_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("pcj"),
        comment="对外任务ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    activity_id = Column(
        BigInteger,
        ForeignKey("crm_customer_activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户活动ID",
    )
    activity_revision = Column(Integer, nullable=False, comment="活动后处理修订号")
    trigger_type = Column(String(80), nullable=False, comment="触发类型")
    actor_id = Column(String(100), nullable=True, comment="触发用户ID")
    status = Column(
        String(20),
        nullable=False,
        default=CustomerActivityPostCommitJobStatus.QUEUED,
        index=True,
        comment="执行状态",
    )
    attempt_count = Column(Integer, nullable=False, default=0, comment="执行次数")
    next_attempt_at = Column(DateTime, nullable=True, index=True, comment="下次恢复时间")
    lease_token = Column(String(64), nullable=True, index=True, comment="当前执行租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="当前执行租约过期时间")
    run_id = Column(String(100), nullable=False, index=True, comment="稳定LangGraph运行ID")
    graph_thread_id = Column(String(240), nullable=False, index=True, comment="LangGraph线程ID")
    result_json = Column(JSON, nullable=True, comment="执行结果")
    error_message = Column(Text, nullable=True, comment="最近错误")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="首次开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "activity_id",
            "trigger_type",
            "activity_revision",
            name="uq_customer_activity_post_commit_job_revision",
        ),
        Index(
            "idx_customer_activity_post_commit_recovery",
            "status",
            "next_attempt_at",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        Index(
            "idx_customer_activity_post_commit_activity",
            "team_id",
            "activity_id",
            "activity_revision",
        ),
        {"comment": "客户活动后提交持久任务表"},
    )
