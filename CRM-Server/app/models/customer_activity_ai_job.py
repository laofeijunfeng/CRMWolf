"""Durable jobs for form-submitted customer-activity AI finalization."""

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
from app.services.customer_activity_contracts import CustomerActivityAIJobStatus
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class CustomerActivityAIJob(Base):
    """One durable structuring-and-evaluation attempt stream per activity revision."""

    __tablename__ = "crm_customer_activity_ai_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("caij"),
        comment="对外任务ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    activity_id = Column(BigInteger, nullable=False, index=True, comment="客户活动ID快照")
    activity_revision = Column(Integer, nullable=False, comment="待最终化的活动修订号")
    job_type = Column(String(40), nullable=False, default="STRUCTURE_AND_EVALUATE", comment="任务类型")
    submission_source = Column(String(32), nullable=False, comment="活动提交来源")
    status = Column(
        String(20),
        nullable=False,
        default=CustomerActivityAIJobStatus.QUEUED.value,
        index=True,
        comment="任务状态",
    )
    attempt_count = Column(Integer, nullable=False, default=0, comment="执行次数")
    next_attempt_at = Column(DateTime, nullable=True, index=True, comment="下次恢复时间")
    lease_token = Column(String(64), nullable=True, index=True, comment="当前执行租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="当前执行租约过期时间")
    run_id = Column(String(100), nullable=False, index=True, comment="稳定运行ID")
    graph_thread_id = Column(String(240), nullable=False, index=True, comment="LangGraph线程ID")
    result_json = Column(JSON, nullable=True, comment="最终结果摘要")
    error_message = Column(Text, nullable=True, comment="最近错误")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="首次开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")

    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRY_PENDING', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
            name="ck_customer_activity_ai_job_status",
        ),
        CheckConstraint(
            "submission_source IN ('FORM', 'CUTOVER_MIGRATION')",
            name="ck_customer_activity_ai_job_submission_source",
        ),
        UniqueConstraint(
            "team_id",
            "activity_id",
            "activity_revision",
            "job_type",
            name="uq_customer_activity_ai_job_revision",
        ),
        Index(
            "idx_customer_activity_ai_job_recovery",
            "status",
            "next_attempt_at",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        Index(
            "idx_customer_activity_ai_job_activity",
            "team_id",
            "activity_id",
            "activity_revision",
        ),
        {"comment": "页面客户活动 AI 整理评分持久任务表"},
    )
