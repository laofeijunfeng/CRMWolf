"""Durable Agent-only opportunity suggestion jobs sourced from customer activities."""

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
from app.services.customer_activity_contracts import (
    CustomerActivitySuggestionJobStatus,
)
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class CustomerOpportunitySuggestionJob(Base):
    """One revision-scoped, Agent-originated opportunity suggestion attempt stream.

    The activity ID is deliberately a non-FK snapshot.  Activity deletion must
    preserve this durable execution evidence and turn unfinished work into a
    terminal ``SKIPPED`` record instead of cascading it away.
    """

    __tablename__ = "crm_customer_opportunity_suggestion_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("cosj"),
        comment="对外任务ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    activity_id = Column(BigInteger, nullable=False, index=True, comment="客户活动ID快照")
    activity_revision = Column(Integer, nullable=False, comment="活动语义修订号")
    submission_source = Column(String(32), nullable=False, comment="活动提交来源")
    status = Column(
        String(20),
        nullable=False,
        default=CustomerActivitySuggestionJobStatus.QUEUED.value,
        index=True,
        comment="任务状态",
    )
    attempt_count = Column(Integer, nullable=False, default=0, comment="执行次数")
    next_attempt_at = Column(DateTime, nullable=True, index=True, comment="下次恢复时间")
    lease_token = Column(String(64), nullable=True, index=True, comment="当前执行租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="当前执行租约过期时间")
    run_id = Column(String(100), nullable=False, index=True, comment="稳定运行ID")
    graph_thread_id = Column(String(240), nullable=False, index=True, comment="LangGraph线程ID")
    result_json = Column(JSON, nullable=True, comment="建议结果")
    error_message = Column(Text, nullable=True, comment="最近错误")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="首次开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")

    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRY_PENDING', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
            name="ck_customer_opportunity_suggestion_job_status",
        ),
        CheckConstraint(
            "submission_source = 'AGENT'",
            name="ck_customer_opportunity_suggestion_job_submission_source",
        ),
        UniqueConstraint(
            "team_id",
            "activity_id",
            "activity_revision",
            name="uq_customer_opportunity_suggestion_job_activity_revision",
        ),
        Index(
            "idx_customer_opportunity_suggestion_job_recovery",
            "status",
            "next_attempt_at",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        Index(
            "idx_customer_opportunity_suggestion_job_activity",
            "team_id",
            "activity_id",
            "activity_revision",
        ),
        {"comment": "客户活动 Agent 商机建议持久任务表"},
    )
